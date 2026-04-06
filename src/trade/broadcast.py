from py_clob_client.clob_types import MarketOrderArgs, OrderType

from src.config import getLogger
from src.trade.models import Trade

logger = getLogger(__name__)


def broadcast_trade(trade: Trade):
    logger.warning("A trade would have been broadcasted!", extra=trade.to_dict())


# if strategy_file is not None and trading_toggle.is_enabled(strategy_file):
#     # only execute a trade if trading is enabled for the given strategy file. trading is only
#     # available for strategy files.
#     # order = client.create_market_order(
#     #     MarketOrderArgs(
#     #         token_id=new_trade.clob,
#     #         # hard-coded at the minimum bet i can do for now...
#     #         amount=1,
#     #         side=new_trade.side.name.upper(),
#     #         # slippage ceiling — won't pay more than this (set super high because my strategies
#     #         # operate near 1.0 dollar markets. This should really be specified in the strategy file somehow.)
#     #         price=0.99,
#     #     )
#     # )
#     # response = client.post_order(order, OrderType.FOK)  # type: ignore
#     response = {"fake": "order response!"}
#     if "status" in response and "status" == "matched":
#         logger.info(
#             "LIVE TRADING: (%s $%s of %s at %s).",
#             str(new_trade.side.name).upper(),
#             str(new_trade.amount),
#             str(new_trade.outcome.name).upper(),
#             str(new_trade.price),
#         )
#     else:
#         logger.info(
#             "LIVE TRADING: Tried to (%s $%s of %s at %s) but order was cancelled (probably not enough liquidity).",
#             str(new_trade.side.name).upper(),
#             str(new_trade.amount),
#             str(new_trade.outcome.name).upper(),
#             str(new_trade.price),
#         )

#     if not isinstance(response, dict):
#         # make sure response is a dictionary
#         raise ValueError("Got bad response from clob client after posting a market order: %s", response)

#     Path("trading_logs").mkdir(exist_ok=True)
#     strategy_name = strategy_file.split(".py")[0]
#     with open(f"trading_logs/{strategy_name}.jsonl", "w") as file:
#         # log the trade!
#         file.write(dumps(response | {"slug": slug}))
#     else:
#     logger.info(
#         "(%s $%s of %s at %s).",
#         str(new_trade.side.name).upper(),
#         str(new_trade.amount),
#         str(new_trade.outcome.name).upper(),
#         str(new_trade.price),
#     )
