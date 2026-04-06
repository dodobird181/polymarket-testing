from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from enum import Enum
from uuid import uuid4


@dataclass(kw_only=True)
class Trade:
    """
    A buy or sell trading signal that can be transmitted to Polymarket.
    """

    class Side(Enum):
        BUY = "buy"
        SELL = "sell"

    class Outcome(Enum):
        UP = "up"
        DOWN = "down"

    id: str = field(default_factory=lambda: str(uuid4()), kw_only=True)
    outcome: Outcome
    clob: str
    side: Side
    amount: float
    price: float

    # datetime for logging
    dt: float

    def display_str(self) -> str:
        return f"{self.side} ${self.amount} of {self.outcome.name} at ${self.price}"

    def to_dict(self) -> dict:
        return asdict(self) | {"outcome": self.outcome.value, "side": self.side.value}

    @classmethod
    def from_dict(cls, d: dict) -> "Trade":
        return cls(
            **{field.name: d[field.name] for field in fields(Trade)}
            | {"outcome": Trade.Outcome(d["outcome"]), "side": Trade.Side(d["side"])}
        )


if __name__ == "__main__":
    t = Trade(
        outcome=Trade.Outcome.DOWN,
        clob="FAKE_CLOB",
        side=Trade.Side.BUY,
        price=0.9,
        amount=100,
        dt=datetime.now().timestamp(),
    )
    print(t)
    d = t.to_dict()
    print(d)
    t = Trade.from_dict(d)
    print(t)
