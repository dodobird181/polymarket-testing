from py_clob_client.client import ClobClient

from src.config import load_config

config = load_config()


class NoClient(Exception):
    """
    Could not create a clob client.
    """

    ...


def get_clob_client():
    try:
        host = "https://clob.polymarket.com"
        chain_id = 137  # Polygon mainnet

        # Derive API credentials (L1 → L2 auth)
        temp_client = ClobClient(host, key=config.polymarket.private_key, chain_id=chain_id)
        api_creds = temp_client.create_or_derive_api_creds()

        # Initialize trading client
        return ClobClient(
            host,
            key=config.polymarket.private_key,
            chain_id=chain_id,
            creds=api_creds,
            # I'm going with the proxy wallet through polymarket to avoid paying gas fees. This seemed like the best
            # one to use from: https://docs.polymarket.com/trading/overview#signature-types.
            signature_type=1,
            funder=config.polymarket.wallet_address,
        )

    except Exception as e:
        raise NoClient from e
