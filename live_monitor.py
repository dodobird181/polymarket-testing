from dataclasses import dataclass
from enum import Enum
from time import sleep
from typing import Callable

from py_clob_client.clob_types import OrderType

from clob_client import get_client
from market_info import (
    Btc5MinClobs,
    current_window_start,
    elapsed,
    get_current_market_clobs,
    to_EST,
)


@dataclass
class LiveMarketState:
    """
    The current state of a live BTC 5-min market.
    """

    @dataclass
    class EstimatedPrice:
        up: float
        down: float

    start_ts: int
    start_EST: str
    elapsed_seconds: int

    price: EstimatedPrice
    clobs: Btc5MinClobs


@dataclass
class Trade:
    """
    A buy or sell trading signal that can be transmitted to Polymarket.
    """

    class Side(Enum):
        BUY = "BUY"
        SELL = "SELL"

    clob: str
    side: Side
    amount: float


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


def run_sam_strategy(state: LiveMarketState) -> Strategy.Result:

    def get_window():
        if state.elapsed_seconds < 120:
            return "before"
        elif state.elapsed_seconds >= 120 and state.elapsed_seconds < 240:
            return "can_trigger"
        else:
            return "after"

    def in_buy_threshold(price: float, min=0.9, max=0.95) -> bool:
        return price >= min and price <= max

    def get_buy_amount():
        return 10

    trade = None
    window = get_window()
    if window == "can_trigger":
        if in_buy_threshold(state.price.up):
            trade = Trade(
                clob=state.clobs.up,
                side=Trade.Side.BUY,
                amount=get_buy_amount(),
            )
        elif in_buy_threshold(state.price.down):
            trade = Trade(
                clob=state.clobs.down,
                side=Trade.Side.BUY,
                amount=get_buy_amount(),
            )

    return Strategy.Result(trade, {"window": window})


if __name__ == "__main__":

    client = get_client()
    clobs = get_current_market_clobs()
    strategy = Strategy(run=run_sam_strategy)
    order_status = None

    while True:
        start_ts = current_window_start()
        state = LiveMarketState(
            start_ts=start_ts,
            start_EST=to_EST(start_ts),
            elapsed_seconds=elapsed(start_ts),
            price=LiveMarketState.EstimatedPrice(
                up=client.calculate_market_price(
                    token_id=clobs.up,
                    side="BUY",
                    amount=10,
                    order_type=OrderType.FOK,  # type: ignore
                ),
                down=client.calculate_market_price(
                    token_id=clobs.down,
                    side="BUY",
                    amount=10,
                    order_type=OrderType.FOK,  # type: ignore
                ),
            ),
            clobs=clobs,
        )
        result = strategy.run(state)
        print(
            f"\r{state.start_EST} {state.elapsed_seconds}s {state.price.__dict__}, {result.metadata}",
            end="",
            flush=True,
        )
        sleep(0.1)
