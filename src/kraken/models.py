from dataclasses import asdict, dataclass
from datetime import datetime


@dataclass
class KrakenData:
    """
    BTC price kraken data.

    NOTE:   This is not always 100% accurate because polymarket gets their price directly
            from the blockchain. It is usually within about $5 USD from the polymarket price.

    """

    @dataclass
    class Candle:
        open_time: int  # seconds
        open: float
        high: float
        low: float
        close: float
        vwap: float
        volume: float
        trade_count: int

    # The live market price according to Kraken. NOTE: Updated every second.
    live_price: float

    # The BTC price at the start of the market interval.
    window_start_price: float

    # History is a list of the past ~24 hours (287 5-minute intervals), in aescending order.
    # I.e., history[-1] is the previous 5-min interval from the current market. history[-4]
    # is 4 intervals ago.
    history: list[Candle]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "KrakenData":
        return cls(
            live_price=d["live_price"],
            window_start_price=d["window_start_price"],
            history=[cls.Candle(**c) for c in d["history"]],
        )


if __name__ == "__main__":
    t = KrakenData(
        live_price=60_000,
        history=[
            KrakenData.Candle(
                open_time=int(datetime.now().timestamp()),
                open=100,
                high=101,
                low=98,
                close=99,
                volume=50_000,
                vwap=50000,
                trade_count=17,
            )
        ],
        window_start_price=65_000,
    )
    print(t)
    d = t.to_dict()
    print(d)
    t = KrakenData.from_dict(d)
    print(t)
