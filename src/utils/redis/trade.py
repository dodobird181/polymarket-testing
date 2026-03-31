from dataclasses import dataclass
from datetime import datetime
from json import dumps, loads

from src.config import load_config
from src.trade import Trade
from src.utils.redis.client import get_redis

"""
Describes adding and removing trades from a redis queue. Trades are produced by `live_monitor.py` threads
(i.e. running strategies), consumed by `trade_processor.py`, and then broadcasted.
"""

config = load_config()
redis = get_redis()

PENDING_KEY = config.redis.trade.pending_key
PROCESSING_KEY = config.redis.trade.processing_key


@dataclass
class PendingTrade:

    trade: Trade
    enqueued_at: int

    def to_dict(self) -> dict:
        return {"trade": self.trade.to_dict(), "enqueued_at": self.enqueued_at}

    @classmethod
    def from_dict(cls, d: dict) -> "PendingTrade":
        return cls(trade=Trade.from_dict(d["trade"]), enqueued_at=d["enqueued_at"])


@dataclass
class ProcessingTrade:

    pending_trade: PendingTrade
    started_processing_at: int

    def to_dict(self) -> dict:
        return {
            "pending_trade": self.pending_trade.to_dict(),
            "started_processing_at": self.started_processing_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ProcessingTrade":
        return cls(
            pending_trade=PendingTrade.from_dict(d["pending_trade"]),
            started_processing_at=d["started_processing_at"],
        )


def enqueue_trade(trade: Trade) -> None:
    now = int(datetime.now().timestamp())
    pending = PendingTrade(trade=trade, enqueued_at=now)
    redis.lpush(PENDING_KEY, dumps(pending.to_dict()))


def wait_for_trade_to_process() -> ProcessingTrade:
    raw: bytes = redis.brpop(PENDING_KEY, timeout=0)[1]  # type: ignore
    pending = PendingTrade.from_dict(loads(raw.decode()))
    now = int(datetime.now().timestamp())
    processing_trade = ProcessingTrade(pending_trade=pending, started_processing_at=now)
    redis.lpush(PROCESSING_KEY, dumps(processing_trade.to_dict()))
    return processing_trade


def mark_done(processing_trade: ProcessingTrade) -> None:
    redis.lrem(PROCESSING_KEY, 1, dumps(processing_trade.to_dict()))


def list_pending() -> list[PendingTrade]:
    return [PendingTrade.from_dict(loads(x.decode())) for x in redis.lrange(PENDING_KEY, 0, -1)]  # type: ignore


def list_processing() -> list[ProcessingTrade]:
    return [ProcessingTrade.from_dict(loads(x.decode())) for x in redis.lrange(PROCESSING_KEY, 0, -1)]  # type: ignore


if __name__ == "__main__":
    from src.trade import Trade

    t = Trade(
        outcome=Trade.Outcome.DOWN,
        clob="FAKE_CLOB",
        side=Trade.Side.BUY,
        price=0.9,
        amount=100,
        dt=datetime.now().timestamp(),
    )
    print(t)
    enqueue_trade(t)
    print(list_pending())
