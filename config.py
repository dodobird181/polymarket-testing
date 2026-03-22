from dataclasses import dataclass
from os import environ

from dotenv import load_dotenv


@dataclass
class Config:

    @dataclass
    class Polymarket:
        private_key: str
        wallet_address: str

    polymarket: Polymarket
    redis_url: str


def load_config() -> Config:
    load_dotenv()
    return Config(
        polymarket=Config.Polymarket(
            private_key=environ["POLYMARKET_PRIVATE_KEY"],
            wallet_address=environ["POLYMARKET_USER_WALLET_ADDRESS"],
        ),
        redis_url=environ["REDIS_URL"],
    )
