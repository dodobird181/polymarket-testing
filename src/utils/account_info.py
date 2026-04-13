from py_clob_client.clob_types import AssetType, BalanceAllowanceParams

from src.utils.clob_client import get_clob_client

client = get_clob_client()


def get_polymarket_account_balance() -> float:
    balance_allowance_response = client.get_balance_allowance(
        BalanceAllowanceParams(
            asset_type=AssetType.COLLATERAL,
        )
    )
    return float(balance_allowance_response["balance"]) / 1e6
