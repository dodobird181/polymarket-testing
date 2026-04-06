from dataclasses import asdict, dataclass, field
from typing import Callable

from src.kraken import KrakenData
from src.trade import Trade
from src.utils import Btc5MinMarketInfo


@dataclass(kw_only=True)
class SerializableMarketState:
    """
    A serializable subset of live-market-state.
    """

    @dataclass
    class EstimatedPrice:
        up: float
        down: float

    slug: str
    start_ts: int
    start_EST: str
    elapsed_seconds: int

    price: EstimatedPrice
    trades: list[Trade] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self) | {
            "trades": [
                asdict(trade)
                | {
                    "side": trade.side.value,
                    "outcome": trade.outcome.value,
                }
                for trade in self.trades
            ]
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SerializableMarketState":
        return cls(
            slug=d["slug"],
            start_ts=d["start_ts"],
            start_EST=d["start_EST"],
            elapsed_seconds=d["elapsed_seconds"],
            price=SerializableMarketState.EstimatedPrice(
                up=d["price"]["up"],
                down=d["price"]["down"],
            ),
            trades=[
                Trade(
                    id=trade["id"],
                    outcome=Trade.Outcome(trade["outcome"]),
                    clob=trade["clob"],
                    side=Trade.Side(trade["side"]),
                    amount=trade["amount"],
                    price=trade["price"],
                    dt=trade["dt"],
                )
                for trade in d["trades"]
            ],
        )


@dataclass
class LiveMarketState(SerializableMarketState):
    """
    The current state of a live BTC 5-min market. This is what gets passed to a trading strategy every tick.
    """

    info: Btc5MinMarketInfo
    kraken: KrakenData | None


@dataclass
class Strategy:
    """
    A trading strategy.
    """

    @dataclass
    class Result:
        trade: Trade | None
        metadata: dict

    # defines whether or not to trade at any given moment and provides
    # a dictionary
    run: Callable[[LiveMarketState], Result]
