from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from json import dumps
from pathlib import Path
from time import sleep
from typing import Callable

from py_clob_client.clob_types import OrderType

from clob_client import get_client
from market_info import (
    Btc5MinClobs,
    Btc5MinMarketOutcome,
    current_window_slug,
    current_window_start,
    elapsed,
    get_current_market_clobs,
    get_market_outcome_from_slug,
    to_EST,
)

LOG_FILE = Path("livetest.jsonl")


@dataclass
class Trade:
    """
    A buy or sell trading signal that can be transmitted to Polymarket.
    """

    class Side(Enum):
        BUY = "BUY"
        SELL = "SELL"

    class Outcome(Enum):
        UP = "UP"
        DOWN = "DOWN"

    outcome: Outcome
    clob: str
    side: Side
    amount: float

    # datetime for logging
    dt: datetime = datetime.now()


@dataclass
class LiveMarketState:
    """
    The current state of a live BTC 5-min market.
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
    clobs: Btc5MinClobs
    trade: Trade | None


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
    amount = get_buy_amount()
    if window == "can_trigger":
        if in_buy_threshold(state.price.up):
            trade = Trade(
                outcome=Trade.Outcome.UP,
                clob=state.clobs.up,
                side=Trade.Side.BUY,
                amount=amount,
            )
        elif in_buy_threshold(state.price.down):
            trade = Trade(
                outcome=Trade.Outcome.DOWN,
                clob=state.clobs.down,
                side=Trade.Side.BUY,
                amount=amount,
            )

    return Strategy.Result(trade, {"window": window})


def poll_current_market() -> LiveMarketState:

    # initialize live monitor for the current 5-min market
    client = get_client()
    clobs = get_current_market_clobs()
    strategy = Strategy(run=run_sam_strategy)
    start_ts = current_window_start()
    slug = current_window_slug(start_ts)
    state = LiveMarketState(
        slug=slug,
        start_ts=start_ts,
        start_EST=to_EST(start_ts),
        elapsed_seconds=0,
        price=LiveMarketState.EstimatedPrice(up=0.5, down=0.5),
        clobs=clobs,
        trade=None,
    )

    # start polling for price updates with out strategy
    while True:
        if datetime.now().timestamp() > state.start_ts + 300:
            # exit condition: the market is over
            return state

        strategy_result = strategy.run(state)
        try:
            state = LiveMarketState(
                slug=slug,
                start_ts=state.start_ts,
                start_EST=state.start_EST,
                # re-calculate the elapsed time since the market opened
                elapsed_seconds=elapsed(state.start_ts),
                # re-fetch the live prices from Polymarket
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
                clobs=state.clobs,
                # record a trade in the live market state if one was made
                trade=state.trade if state.trade is not None else strategy_result.trade,
            )
        except Exception:
            return state
        print(
            f"\r{state.slug} {state.elapsed_seconds}s :: {state.price.__dict__} {["BUY", state.trade.amount, state.trade.outcome.value.upper()] if state.trade is not None else "[No Trade]"} {strategy_result.metadata}             ",
            end="",
            flush=True,
        )
        sleep(0.1)


def log_market_outcome(state: LiveMarketState, outcome: Btc5MinMarketOutcome) -> None:
    LOG_FILE.parent.mkdir(exist_ok=True)
    entry = {"state": asdict(state), "outcome": outcome.value}
    with LOG_FILE.open("a") as f:
        f.write(dumps(entry) + "\n")
    print(f"\n  [LOG] {entry}")


if __name__ == "__main__":

    # track past markets to record their outcomes after they've closed
    # key = slug, value = LiveMarketState
    unresolved_markets = {}

    # resolved markets to flush
    flush = []

    while True:

        state = poll_current_market()

        # see if any of the previous markets have been resolved and log
        for old_slug in unresolved_markets:
            old_state: LiveMarketState = unresolved_markets[old_slug]
            outcome = get_market_outcome_from_slug(old_state.slug)
            if outcome == Btc5MinMarketOutcome.UNRESOLVED:
                print(f"WARNING: {old_slug} still unresolved!")
            else:
                log_market_outcome(old_state, outcome)
                flush.append(old_slug)
        for resolved_slug in flush:
            unresolved_markets.pop(resolved_slug)

        if state.slug not in unresolved_markets:
            # stop from adding more market results if they already exist in the unresolved_markets
            # dictionary. this can happen near the edges of when a market is resolved.
            unresolved_markets[state.slug] = state

        # just adding a little buffer here for checking when the new market is open
        # it shoudn't matter for most strategies to get in 2 seconds after market open...
        print(f"Unresolved markets: {unresolved_markets.keys()}.")
        sleep(2)
