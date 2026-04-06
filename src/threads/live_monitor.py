from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path
from sys import path as systempath
from time import sleep

from py_clob_client.clob_types import OrderType

systempath.insert(0, str(Path(__file__).parents[2]))
from src.config import StrategyToggleConfigProvider, getLogger
from src.trade import Trade
from src.utils import (
    Btc5MinMarketOutcome,
    LiveMarketState,
    Strategy,
    current_window_slug,
    current_window_start,
    elapsed,
    enqueue_trade,
    get_clob_client,
    get_current_market_info,
    get_kraken_data,
    to_EST,
)

"""
Entrypoint for a trading strategy.
"""

logger = getLogger(__name__)


# def run_sam_strategy(state: LiveMarketState) -> Strategy.Result:

#     def get_window():
#         if state.elapsed_seconds < 180:
#             return "before"
#         elif state.elapsed_seconds >= 180 and state.elapsed_seconds < 270:
#             return "can_trigger"
#         else:
#             return "after"

#     def in_buy_threshold(price: float, min=0.9, max=0.95) -> bool:
#         return price >= min and price <= max

#     def get_buy_amount():
#         return 10

#     trade = None
#     window = get_window()
#     if len(state.trades) == 0:
#         amount = get_buy_amount()
#         if window == "can_trigger":
#             if in_buy_threshold(state.price.up):
#                 trade = Trade(
#                     outcome=Trade.Outcome.UP,
#                     clob=state.info.up_clob_id,
#                     side=Trade.Side.BUY,
#                     amount=amount,
#                     price=state.price.up,
#                     dt=datetime.now().timestamp(),
#                 )
#             elif in_buy_threshold(state.price.down):
#                 trade = Trade(
#                     outcome=Trade.Outcome.DOWN,
#                     clob=state.info.down_clob_id,
#                     side=Trade.Side.BUY,
#                     amount=amount,
#                     price=state.price.down,
#                     dt=datetime.now().timestamp(),
#                 )

#     return Strategy.Result(trade, {"window": window})


def poll_current_market(strategy: Strategy) -> LiveMarketState:

    # initialize live monitor for the current 5-min market
    client = get_clob_client()
    info = get_current_market_info()
    start_ts = current_window_start()
    startEST = to_EST(start_ts)
    slug = current_window_slug(start_ts)
    state = LiveMarketState(
        slug=slug,
        start_ts=start_ts,
        start_EST=startEST,
        elapsed_seconds=0,
        price=LiveMarketState.EstimatedPrice(up=0.5, down=0.5),
        info=info,
        kraken=get_kraken_data(),
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
            enqueue_trade(
                trade=new_trade,
                state=state,
                strategy_name=strategy.name,
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
                        # TODO: Should probably revisit the order-book depth consequences of using 10 dollars here in the future. Same for below.
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
                kraken=get_kraken_data(),
            )

        except Exception as e:
            logger.debug("Failed to fetch market prices, returning current state.", exc_info=e)
            return state

        sleep(0.1)


def load_strategy_from_file(path: Path) -> Strategy:
    from RestrictedPython import compile_restricted, safe_builtins, safe_globals

    source = Path(path).read_text()
    try:
        compiled = compile_restricted(source, filename=str(path), mode="exec")
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

    return Strategy(name=path.stem, run=restricted_globals["run_strategy"], file=str(path))  # type: ignore[arg-type]


if __name__ == "__main__":

    parser = ArgumentParser(description="Live market monitor")
    parser.add_argument("log_file", type=Path, help="Path to the log file (e.g. livetest.jsonl).")
    parser.add_argument("strategy", type=Path, help="Path to the strategy file (e.g., livetest.py).")
    args = parser.parse_args()

    if args.strategy.suffix == ".py":
        strategy = load_strategy_from_file(args.strategy)
    else:
        raise ValueError("Expected strategy filename to end in '.py'.")

    while True:
        try:
            start_ts = current_window_start()
            slug = current_window_slug(start_ts)
            logger.info("Starting poll for market %s...", slug)
            state = poll_current_market(strategy=strategy)
            logger.info("Poll for market %s has finished. Waiting for next market to open...", slug)

            # # see if any of the previous markets have been resolved and log
            # for old_slug in unresolved_markets:
            #     old_state: LiveMarketState = unresolved_markets[old_slug]
            #     outcome = get_market_outcome_from_slug(old_state.slug)
            #     if outcome == Btc5MinMarketOutcome.UNRESOLVED:
            #         pass
            #     else:
            #         log_market_outcome(old_state, outcome)
            #         flush.append(old_slug)
            # for resolved_slug in flush:
            #     if resolved_slug in unresolved_markets:
            #         unresolved_markets.pop(resolved_slug)

            # if state.slug not in unresolved_markets:
            #     # stop from adding more market results if they already exist in the unresolved_markets
            #     # dictionary. this can happen near the edges of when a market is resolved.
            #     unresolved_markets[state.slug] = state
            # else:
            #     logger.debug(f"Strategy exited early for market {slug}. Waiting for next market to open...")

            # just adding a little buffer here for checking when the new market is open
            # it shoudn't matter for most strategies to get in 5 seconds after market open...
            # logger.debug(f"Unresolved markets: {[x for x in unresolved_markets.keys()]}.")
        except Exception as e:
            logger.error("Something went wrong while running strategy: %s", strategy.name, exc_info=e)
        sleep(5)
