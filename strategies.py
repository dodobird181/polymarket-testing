from datetime import datetime
from json import loads
from typing import Callable

from live_monitor import LiveMarketState, Strategy, Trade
from log_config import getLogger

logger = getLogger(__name__)


def strategy_from_params(
    window_start: int,
    window_end: int,
    min_buy_price: float,
    max_buy_price: float,
    stop_loss_price: float,
) -> Callable[[LiveMarketState], Strategy.Result]:

    def _strategy(state: LiveMarketState) -> Strategy.Result:

        def get_window():
            if state.elapsed_seconds < window_start:
                return "before"
            elif state.elapsed_seconds >= window_start and state.elapsed_seconds < window_end:
                return "can_trigger"
            else:
                return "after"

        def in_buy_threshold(price: float, min=min_buy_price, max=max_buy_price) -> bool:
            return price >= min and price <= max

        trade = None
        window = get_window()
        amount = 10
        if len(state.trades) == 0:
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
        elif len(state.trades) == 1:
            # protect downside losses by selling
            buy_trade = state.trades[0]
            if buy_trade.outcome == Trade.Outcome.UP and state.price.up <= stop_loss_price:
                trade = Trade(
                    outcome=Trade.Outcome.UP,
                    clob=state.clobs.up,
                    side=Trade.Side.SELL,
                    amount=buy_trade.amount,
                    price=state.price.up,
                    dt=datetime.now().timestamp(),
                )
            elif buy_trade.outcome == Trade.Outcome.DOWN and state.price.down <= stop_loss_price:
                trade = Trade(
                    outcome=Trade.Outcome.DOWN,
                    clob=state.clobs.down,
                    side=Trade.Side.SELL,
                    amount=buy_trade.amount,
                    price=state.price.down,
                    dt=datetime.now().timestamp(),
                )

        return Strategy.Result(trade, {"window": window})

    return lambda state: _strategy(state)


def load_strategy_from_param_file(filename: str) -> Strategy:
    with open(filename, "r") as file:
        params = loads(file.read())
        logger.debug(f"Loading strategy from params: {params}")
        return Strategy(run=strategy_from_params(**params))
