from dataclasses import dataclass
from dataclasses import fields as dataclass_fields
from datetime import datetime
from json import dumps, loads
from typing import Type

from src.config import getLogger, load_config
from src.trade import Trade
from src.utils.redis.client import get_redis
from src.utils.strategy import SerializableMarketState

"""
Describes adding and removing trades from a redis queue. Trades are produced by `live_monitor.py` threads
(i.e. running strategies), consumed by `trade_processor.py`, and then broadcasted.
"""

logger = getLogger(__name__)
config = load_config()
redis = get_redis()

PENDING_KEY = config.redis.trade.pending_key
PROCESSING_KEY = config.redis.trade.processing_key


def _parent_kwargs_from_dict(d: dict, parent_class: Type) -> dict:
    parent = parent_class.from_dict(d)
    return {field.name: getattr(parent, field.name) for field in dataclass_fields(parent_class)}


@dataclass
class PendingTrade(Trade):

    state: SerializableMarketState
    strategy_name: str
    enqueued_at: float

    def to_dict(self) -> dict:
        return super().to_dict() | {
            "state": self.state.to_dict(),
            "strategy_name": self.strategy_name,
            "enqueued_at": self.enqueued_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PendingTrade":
        return cls(
            state=SerializableMarketState.from_dict(d["state"]),
            strategy_name=d["strategy_name"],
            enqueued_at=d["enqueued_at"],
            **_parent_kwargs_from_dict(d, Trade),
        )


@dataclass
class ProcessingTrade(PendingTrade):

    started_processing_at: float

    def to_dict(self) -> dict:
        return super().to_dict() | {
            "started_processing_at": self.started_processing_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ProcessingTrade":
        return cls(
            started_processing_at=d["started_processing_at"],
            **_parent_kwargs_from_dict(d, PendingTrade),
        )


@dataclass
class CompletedTrade(ProcessingTrade):

    completed_at: float

    def to_dict(self) -> dict:
        return super().to_dict() | {
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CompletedTrade":
        return cls(
            completed_at=d["completed_at"],
            **_parent_kwargs_from_dict(d, ProcessingTrade),
        )


def enqueue_trade(trade: Trade, state: SerializableMarketState, strategy_name: str) -> None:
    """
    Build and add a pending-trade to the queue for processing.
    """
    now = datetime.now().timestamp()
    pending = PendingTrade.from_dict(
        trade.to_dict()
        | {
            "state": state.to_dict(),
            "strategy_name": strategy_name,
            "enqueued_at": now,
        }
    )
    redis.lpush(PENDING_KEY, dumps(pending.to_dict()))
    logger.debug("Enqueued trade '%s' to redis queue '%s'.", trade.id[:4], PENDING_KEY)


def wait_for_trade_to_process() -> ProcessingTrade:
    """
    Wait for a pending trade to move it to the processing queue.
    NOTE: This is a blocking function call.
    """
    raw: bytes = redis.brpop(PENDING_KEY, timeout=0)[1]  # type: ignore
    pending_trade = PendingTrade.from_dict(loads(raw.decode()))
    processing_trade = ProcessingTrade.from_dict(
        pending_trade.to_dict()
        | {
            "started_processing_at": datetime.now().timestamp(),
        }
    )
    redis.lpush(PROCESSING_KEY, dumps(processing_trade.to_dict()))
    logger.debug("Processing trade '%s' in redis queue '%s'.", processing_trade.id[:4], PROCESSING_KEY)
    return processing_trade


def mark_completed(processing_trade: ProcessingTrade) -> CompletedTrade:
    """
    Remove the trade from the processing queue and return a completed-trade.
    """
    redis.lrem(PROCESSING_KEY, 1, dumps(processing_trade.to_dict()))
    completed_trade = CompletedTrade.from_dict(
        processing_trade.to_dict()
        | {
            "completed_at": datetime.now().timestamp(),
        }
    )
    logger.debug("Completed trade: %s.", processing_trade.id[:4])
    return completed_trade


def list_pending() -> list[PendingTrade]:
    return [PendingTrade.from_dict(loads(x.decode())) for x in redis.lrange(PENDING_KEY, 0, -1)]  # type: ignore


def list_processing() -> list[ProcessingTrade]:
    return [ProcessingTrade.from_dict(loads(x.decode())) for x in redis.lrange(PROCESSING_KEY, 0, -1)]  # type: ignore


if __name__ == "__main__":
    from src.config import getLogger
    from src.trade import Trade

    logger = getLogger(__name__)

    new_trade = Trade(
        outcome=Trade.Outcome.DOWN,
        clob="FAKE_CLOB",
        side=Trade.Side.SELL,
        price=0.23,
        amount=50,
        dt=datetime.now().timestamp(),
    )
    state = SerializableMarketState(
        slug="btc-updown-5m-1774070400",
        start_ts=1774070400,
        start_EST="2026-03-21 01:20:00 AM EST",
        # pretend we are 2 minutes and 6 seconds into the current market window
        elapsed_seconds=126,
        price=SerializableMarketState.EstimatedPrice(up=0.3, down=0.7),
        trades=[
            # pretend there is already a trade in the current market state to simulate
            # a little closer to real runtime complexity.
            Trade(
                outcome=Trade.Outcome.DOWN,
                clob="FAKE_CLOB",
                side=Trade.Side.BUY,
                price=0.9,
                amount=100,
                dt=datetime.now().timestamp(),
            )
        ],
    )

    logger.info("Enqueueing new trade: %s", dumps(new_trade.to_dict(), indent=2))
    enqueue_trade(new_trade, state, "fake_strategy_name")
    logger.info("Pending trades: %s", dumps({"pending": [x.to_dict() for x in list_pending()]}, indent=2))
    logger.info("Processing trades: %s", dumps({"processing": [x.to_dict() for x in list_processing()]}, indent=2))
