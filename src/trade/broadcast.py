from json import dumps
from pathlib import Path

from py_clob_client.clob_types import MarketOrderArgs, OrderType

from src.config import getLogger, load_config
from src.utils.account_info import get_polymarket_account_balance
from src.utils.clob_client import get_clob_client
from src.utils.redis.trade import ProcessingTrade

logger = getLogger(__name__)
config = load_config()
client = get_clob_client()

TRADE_LOGFILE = "all_trades.jsonl"


def broadcast_trade(trade: ProcessingTrade):
    logger.info("BROADCASTING TRADE: [%s].", trade.display_str())
    order = client.create_market_order(
        MarketOrderArgs(
            token_id=trade.clob,
            amount=trade.amount,
            side=trade.side.value.upper(),
            price=0.98,  # slippage ceiling — won't pay more than this
        )
    )
    response = client.post_order(order, OrderType.FOK)  # type: ignore
    if not isinstance(response, dict):
        raise AssertionError(
            "Expected Polymarket API order response to be a dict! This trade will not be logged :("
        )

    logpath = Path(config.strategy.log_dir).parent / TRADE_LOGFILE
    with open(logpath, "a") as logfile:
        logfile.write(dumps(response | {"current_balance": get_polymarket_account_balance()}))
