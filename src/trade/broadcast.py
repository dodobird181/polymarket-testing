from py_clob_client.clob_types import MarketOrderArgs, OrderType

from src.trade.models import Trade


def broadcast_trade(trade: Trade): ...
