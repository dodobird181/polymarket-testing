from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from json import dumps, loads
from pathlib import Path
from sys import argv
from time import sleep
from typing import Callable

from py_clob_client.clob_types import MarketOrderArgs, OrderType

from clob_client import get_client
from src.config import StrategyToggleConfigProvider, getLogger
from src.utils import get_redis
from src.utils.market_info import (
    Btc5MinMarketInfo,
    Btc5MinMarketOutcome,
    current_window_slug,
    current_window_start,
    elapsed,
    get_current_market_info,
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

    slug: str
    start_ts: int
    start_EST: str
    elapsed_seconds: int

    price: EstimatedPrice
    info: Btc5MinMarketInfo
    kraken: KrakenData | None
    trades: list[Trade] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self) | {
            "trades": [asdict(t) | {"side": t.side.value, "outcome": t.outcome.value} for t in self.trades]
        }
        # exclude kraken BTC price information when logging the current market session
        d.pop("kraken")
        return d


def read_kraken_data() -> LiveMarketState.KrakenData | None:
    try:
        redis = get_redis()
        raw_live, raw_history = redis.get("kraken:live"), redis.get("kraken:history")
        if raw_live is None or raw_history is None:
            return None
        data = loads(raw_live)  # type: ignore[arg-type]
        Candle = LiveMarketState.KrakenData.Candle
        return LiveMarketState.KrakenData(
            live_price=data["live_price"],
            window_start_price=data["window_start_price"],
            history=[
                Candle(
                    open_time=k[0],
                    open=float(k[1]),
                    high=float(k[2]),
                    low=float(k[3]),
                    close=float(k[4]),
                    vwap=float(k[5]),
                    volume=float(k[6]),
                    trade_count=k[7],
                )
                for k in loads(raw_history)  # type: ignore[arg-type]
            ],
        )
    except Exception as e:
        logger.warning("Failed to load kraken data.", exc_info=e)
        return None


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
                    clob=state.info.up_clob_id,
                    side=Trade.Side.BUY,
                    amount=amount,
                    price=state.price.up,
                    dt=datetime.now().timestamp(),
                )
            elif in_buy_threshold(state.price.down):
                trade = Trade(
                    outcome=Trade.Outcome.DOWN,
                    clob=state.info.down_clob_id,
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
                    clob=state.info.up_clob_id,
                    side=Trade.Side.BUY,
                    amount=amount,
                    price=state.price.up,
                    dt=datetime.now().timestamp(),
                )
            elif in_buy_threshold(state.price.down):
                trade = Trade(
                    outcome=Trade.Outcome.DOWN,
                    clob=state.info.down_clob_id,
                    side=Trade.Side.BUY,
                    amount=amount,
                    price=state.price.down,
                    dt=datetime.now().timestamp(),
                )

    return Strategy.Result(trade, {"window": window})


def poll_current_market(strategy: Strategy, strategy_file: str | None) -> LiveMarketState:

    # initialize live monitor for the current 5-min market
    client = get_client()
    info = get_current_market_info()
    start_ts = current_window_start()
    startEST = to_EST(start_ts)
    slug = current_window_slug(start_ts)
    trading_toggle = StrategyToggleConfigProvider().get().trading
    state = LiveMarketState(
        slug=slug,
        start_ts=start_ts,
        start_EST=startEST,
        elapsed_seconds=0,
        price=LiveMarketState.EstimatedPrice(up=0.5, down=0.5),
        info=info,
        kraken=read_kraken_data(),
    )

    # start polling for price updates with out strategy
    while True:
        if datetime.now().timestamp() > state.start_ts + 300:
            # exit condition: the market is over
            return state

        strategy_result = strategy.run(state)
        total_trades = [*state.trades]
        if strategy_result.trade is not None:
            new_trade = strategy_result.trade
            total_trades.append(new_trade)
            if strategy_file is not None and trading_toggle.is_enabled(strategy_file):
                # only execute a trade if trading is enabled for the given strategy file. trading is only
                # available for strategy files.
                # order = client.create_market_order(
                #     MarketOrderArgs(
                #         token_id=new_trade.clob,
                #         # hard-coded at the minimum bet i can do for now...
                #         amount=1,
                #         side=new_trade.side.name.upper(),
                #         # slippage ceiling — won't pay more than this (set super high because my strategies
                #         # operate near 1.0 dollar markets. This should really be specified in the strategy file somehow.)
                #         price=0.99,
                #     )
                # )
                # response = client.post_order(order, OrderType.FOK)  # type: ignore
                response = {"fake": "order response!"}
                if "status" in response and "status" == "matched":
                    logger.info(
                        "LIVE TRADING: (%s $%s of %s at %s).",
                        str(new_trade.side.name).upper(),
                        str(new_trade.amount),
                        str(new_trade.outcome.name).upper(),
                        str(new_trade.price),
                    )
                else:
                    logger.info(
                        "LIVE TRADING: Tried to (%s $%s of %s at %s) but order was cancelled (probably not enough liquidity).",
                        str(new_trade.side.name).upper(),
                        str(new_trade.amount),
                        str(new_trade.outcome.name).upper(),
                        str(new_trade.price),
                    )

                if not isinstance(response, dict):
                    # make sure response is a dictionary
                    raise ValueError("Got bad response from clob client after posting a market order: %s", response)

                Path("trading_logs").mkdir(exist_ok=True)
                strategy_name = strategy_file.split(".py")[0]
                with open(f"trading_logs/{strategy_name}.jsonl", "w") as file:
                    # log the trade!
                    file.write(dumps(response | {"slug": slug}))
            else:
                logger.info(
                    "(%s $%s of %s at %s).",
                    str(new_trade.side.name).upper(),
                    str(new_trade.amount),
                    str(new_trade.outcome.name).upper(),
                    str(new_trade.price),
                )
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
                        token_id=info.up_clob_id,
                        side="BUY",
                        amount=10,
                        order_type=OrderType.FOK,  # type: ignore
                    ),
                    down=client.calculate_market_price(
                        token_id=info.down_clob_id,
                        side="BUY",
                        amount=10,
                        order_type=OrderType.FOK,  # type: ignore
                    ),
                ),
                info=state.info,
                # append new trade to list if one was signaled
                trades=total_trades,
                kraken=read_kraken_data(),
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
    # logger.info(dumps(entry, indent=2))


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
        try:
            start_ts = current_window_start()
            slug = current_window_slug(start_ts)
            if STRATEGY_FILE:
                STRATEGY = load_strategy_from_file(STRATEGY_FILE)

            if slug not in unresolved_markets:

                logger.info("Starting poll for market %s.", slug)

                state = poll_current_market(strategy=STRATEGY, strategy_file=STRATEGY_FILE)

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
        except Exception as e:
            logger.error("Something went wrong while trading: %s", STRATEGY.run.__name__, exc_info=e)
            sleep(5)
            sleep(5)
