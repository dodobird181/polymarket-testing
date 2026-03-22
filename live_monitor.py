from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from json import dumps
from pathlib import Path
from sys import argv
from time import sleep
from typing import Callable

from py_clob_client.clob_types import OrderType

from clob_client import get_client
from log_config import getLogger
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

logger = getLogger(__name__)


@dataclass
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

    outcome: Outcome
    clob: str
    side: Side
    amount: float
    price: float

    # datetime for logging
    dt: float

    def display_str(self) -> str:
        return f"{self.side} ${self.amount} of {self.outcome.name} at ${self.price}"


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
    trades: list[Trade] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self) | {
            "trades": [asdict(t) | {"side": t.side.value, "outcome": t.outcome.value} for t in self.trades]
        }


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
        if state.elapsed_seconds < 180:
            return "before"
        elif state.elapsed_seconds >= 180 and state.elapsed_seconds < 270:
            return "can_trigger"
        else:
            return "after"

    def in_buy_threshold(price: float, min=0.9, max=0.95) -> bool:
        return price >= min and price <= max

    def get_buy_amount():
        return 10

    trade = None
    window = get_window()
    if len(state.trades) == 0:
        amount = get_buy_amount()
        if window == "can_trigger":
            if in_buy_threshold(state.price.up):
                trade = Trade(
                    outcome=Trade.Outcome.UP,
                    clob=state.clobs.up,
                    side=Trade.Side.BUY,
                    amount=amount,
                    price=state.price.up,
                    dt=datetime.now().timestamp(),
                )
            elif in_buy_threshold(state.price.down):
                trade = Trade(
                    outcome=Trade.Outcome.DOWN,
                    clob=state.clobs.down,
                    side=Trade.Side.BUY,
                    amount=amount,
                    price=state.price.down,
                    dt=datetime.now().timestamp(),
                )

    return Strategy.Result(trade, {"window": window})


def run_sam_strategy_higher_buy_threshold(state: LiveMarketState) -> Strategy.Result:

    def get_window():
        if state.elapsed_seconds < 180:
            return "before"
        elif state.elapsed_seconds >= 180 and state.elapsed_seconds < 300:
            return "can_trigger"
        else:
            return "after"

    def in_buy_threshold(price: float, min=0.95, max=0.985) -> bool:
        return price >= min and price <= max

    def get_buy_amount():
        return 10

    trade = None
    window = get_window()
    if len(state.trades) == 0:
        amount = get_buy_amount()
        if window == "can_trigger":
            if in_buy_threshold(state.price.up):
                trade = Trade(
                    outcome=Trade.Outcome.UP,
                    clob=state.clobs.up,
                    side=Trade.Side.BUY,
                    amount=amount,
                    price=state.price.up,
                    dt=datetime.now().timestamp(),
                )
            elif in_buy_threshold(state.price.down):
                trade = Trade(
                    outcome=Trade.Outcome.DOWN,
                    clob=state.clobs.down,
                    side=Trade.Side.BUY,
                    amount=amount,
                    price=state.price.down,
                    dt=datetime.now().timestamp(),
                )

    return Strategy.Result(trade, {"window": window})


def poll_current_market(strategy: Strategy) -> LiveMarketState:

    # initialize live monitor for the current 5-min market
    client = get_client()
    clobs = get_current_market_clobs()
    start_ts = current_window_start()
    startEST = to_EST(start_ts)
    slug = current_window_slug(start_ts)
    state = LiveMarketState(
        slug=slug,
        start_ts=start_ts,
        start_EST=startEST,
        elapsed_seconds=0,
        price=LiveMarketState.EstimatedPrice(up=0.5, down=0.5),
        clobs=clobs,
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
                # append new trade to list if one was signaled
                trades=state.trades + ([strategy_result.trade] if strategy_result.trade is not None else []),
            )
        except Exception:
            return state
        logger.debug(
            f"{state.slug} {state.elapsed_seconds}s :: {state.price.__dict__} {[trade.display_str() for trade in state.trades] if len(state.trades) > 0 else '[No Trades]'} {strategy_result.metadata}"
        )
        sleep(0.1)


def log_market_outcome(state: LiveMarketState, outcome: Btc5MinMarketOutcome) -> None:
    LOG_FILE.parent.mkdir(exist_ok=True)
    entry = {"state": state.to_dict(), "outcome": outcome.value}
    with LOG_FILE.open("a") as f:
        f.write(dumps(entry) + "\n")
    logger.info(dumps(entry, indent=2))


def load_strategy_from_file(path: str) -> Strategy:
    from RestrictedPython import compile_restricted, safe_builtins, safe_globals

    source = Path(path).read_text()
    try:
        compiled = compile_restricted(source, filename=path, mode="exec")
    except SyntaxError as e:
        raise ValueError(f"Strategy has a syntax error: {e}")

    def _no_import(*_):
        raise ImportError("Imports are not allowed in strategies!")

    restricted_globals = {
        **safe_globals,
        "__builtins__": {**safe_builtins, "__import__": _no_import},
        "_getitem_": lambda obj, key: obj[key],
        "datetime": datetime,
        "LiveMarketState": LiveMarketState,
        "Strategy": Strategy,
        "Trade": Trade,
    }

    exec(compiled, restricted_globals)  # noqa: S102

    if "run_strategy" not in restricted_globals:
        raise ValueError(f"{path} must define a function named 'run_strategy'.")

    return Strategy(run=restricted_globals["run_strategy"])  # type: ignore[arg-type]


if __name__ == "__main__":

    DEFAULT_LOGFILE = "livetest.jsonl"
    DEFAULT_STRATEGY = Strategy(run=run_sam_strategy)

    STRATEGY_FILE: str | None = None

    if len(argv) == 3:
        LOG_FILE = Path(argv[1])
        arg = argv[2]
        if arg.endswith(".py") or "/" in arg:
            STRATEGY_FILE = arg
            STRATEGY = load_strategy_from_file(arg)
        else:
            try:
                STRATEGY = Strategy(run=globals()[arg])
            except KeyError:
                raise ValueError(f"Could not find strategy function '{arg}'.")
    elif len(argv) == 2:
        LOG_FILE = Path(argv[1])
        STRATEGY = DEFAULT_STRATEGY
    elif len(argv) == 1:
        LOG_FILE = Path(DEFAULT_LOGFILE)
        STRATEGY = DEFAULT_STRATEGY
    else:
        raise Exception("Usage: python live_monitor.py [logfile_name.jsonl] [strategy_file.py|strategy_func_name]")

    # track past markets to record their outcomes after they've closed
    # key = slug, value = LiveMarketState
    unresolved_markets = {}

    # resolved markets to flush
    flush = []

    while True:

        start_ts = current_window_start()
        slug = current_window_slug(start_ts)
        if STRATEGY_FILE:
            STRATEGY = load_strategy_from_file(STRATEGY_FILE)

        if slug not in unresolved_markets:

            logger.info(
                "Starting poll %s",
                dumps(
                    {
                        "market": slug,
                        "start_EST": to_EST(start_ts),
                        "strategy": STRATEGY.run.__name__,
                        "logfile": LOG_FILE.name,
                    },
                    indent=2,
                ),
            )

            state = poll_current_market(strategy=STRATEGY)

            # see if any of the previous markets have been resolved and log
            for old_slug in unresolved_markets:
                old_state: LiveMarketState = unresolved_markets[old_slug]
                outcome = get_market_outcome_from_slug(old_state.slug)
                if outcome == Btc5MinMarketOutcome.UNRESOLVED:
                    pass
                else:
                    log_market_outcome(old_state, outcome)
                    flush.append(old_slug)
            for resolved_slug in flush:
                if resolved_slug in unresolved_markets:
                    unresolved_markets.pop(resolved_slug)

            if state.slug not in unresolved_markets:
                # stop from adding more market results if they already exist in the unresolved_markets
                # dictionary. this can happen near the edges of when a market is resolved.
                unresolved_markets[state.slug] = state
        else:
            logger.debug(f"Strategy exited early for market {slug}. Waiting for next market to open...")

        # just adding a little buffer here for checking when the new market is open
        # it shoudn't matter for most strategies to get in 5 seconds after market open...
        logger.debug(f"Unresolved markets: {[x for x in unresolved_markets.keys()]}.")
        sleep(5)
