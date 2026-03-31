from dataclasses import dataclass
from logging import INFO, WARNING, Formatter, _nameToLevel, basicConfig, getLogger
from os import environ

from dotenv import load_dotenv

DEFAULT_LOG_LEVEL = INFO
LOG_DATE_FORMAT = "%Y-%m-%d @ %I:%M:%S %p %Z"

DEFAULT_STRATEGY_FILE_DIR = "data/strategy"
DEFAULT_STRATEGY_LOG_DIR = "data/logs"
DEFAULT_STRATEGY_PLOT_DIR = "data/plots"

DEFAULT_REDIS_TRADE_PENDING_KEY = "trade_queue:pending"
DEFAULT_REDIS_TRADE_PROCESSING_KEY = "trade_queue:processing"
DEFAULT_REDIS_KRAKEN_BTC_HISTORY_KEY = "kraken:btc_history"
DEFAULT_REDIS_KRAKEN_BTC_LIVE_PRICE_KEY = "kraken:btc_live_price"


def _resolve_with_fallback(env_key: str, default: str | int | float) -> str | int | float:
    if env_key in environ:
        return environ[env_key]
    return default


def _resolve_log_level_from_environ() -> int:
    """
    Get the log level from the environment, or fallback to the default.
    """
    key = "LOG_LEVEL"
    if key not in environ:
        return DEFAULT_LOG_LEVEL
    elif environ[key] not in _nameToLevel:
        raise ValueError("Unknown log level %s.", environ[key])
    return _nameToLevel[environ[key]]


# a static dictionary that defines which third-party logs need to be silenced.
SILENCE_LOGS = {
    "httpx": WARNING,
    "httpcore": WARNING,
    "hpack": WARNING,
    "urllib3": WARNING,
    "watchdog": INFO,
    "matplotlib": INFO,
    "PIL": INFO,
}


@dataclass
class Config:

    @dataclass
    class Polymarket:
        private_key: str
        wallet_address: str

    @dataclass
    class Strategy:
        file_dir: str
        log_dir: str
        plot_dir: str

    @dataclass
    class Redis:

        @dataclass
        class Trade:
            pending_key: str
            processing_key: str

        @dataclass
        class Kraken:
            btc_history_key: str
            btc_live_price_key: str

        trade: Trade
        kraken: Kraken
        url: str

    polymarket: Polymarket
    strategy: Strategy
    redis: Redis
    log_level: int


_config = None


def load_config() -> Config:
    global _config
    if _config is None:
        load_dotenv()
        if environ["REDIS_KEY_PREFIX"] is None:
            raise Exception("REDIS_KEY_PREFIX missing from environment.")
        else:
            redis_key_prefix = environ["REDIS_KEY_PREFIX"]
        _config = Config(
            polymarket=Config.Polymarket(
                private_key=environ["POLYMARKET_PRIVATE_KEY"],
                wallet_address=environ["POLYMARKET_USER_WALLET_ADDRESS"],
            ),
            strategy=Config.Strategy(
                file_dir=str(_resolve_with_fallback("STRATEGY_FILE_DIR", DEFAULT_STRATEGY_FILE_DIR)),
                log_dir=str(_resolve_with_fallback("STRATEGY_LOG_DIR", DEFAULT_STRATEGY_LOG_DIR)),
                plot_dir=str(_resolve_with_fallback("STRATEGY_PLOT_DIR", DEFAULT_STRATEGY_PLOT_DIR)),
            ),
            redis=Config.Redis(
                url=environ["REDIS_URL"],
                trade=Config.Redis.Trade(
                    pending_key=redis_key_prefix
                    + str(_resolve_with_fallback("REDIS_TRADE_PENDING_KEY", DEFAULT_REDIS_TRADE_PENDING_KEY)),
                    processing_key=redis_key_prefix
                    + str(_resolve_with_fallback("REDIS_TRADE_PROCESSING_KEY", DEFAULT_REDIS_TRADE_PROCESSING_KEY)),
                ),
                kraken=Config.Redis.Kraken(
                    btc_history_key=redis_key_prefix
                    + str(
                        _resolve_with_fallback("REDIS_KRAKEN_BTC_HISTORY_KEY", DEFAULT_REDIS_KRAKEN_BTC_HISTORY_KEY)
                    ),
                    btc_live_price_key=redis_key_prefix
                    + str(
                        _resolve_with_fallback(
                            "REDIS_KRAKEN_BTC_LIVE_PRICE_KEY", DEFAULT_REDIS_KRAKEN_BTC_LIVE_PRICE_KEY
                        )
                    ),
                ),
            ),
            log_level=_resolve_log_level_from_environ(),
        )
        basicConfig(
            level=_config.log_level,
            format="(%(asctime)s) %(levelname)s: %(message)s",
            datefmt=LOG_DATE_FORMAT,
        )
        [getLogger(module).setLevel(level) for module, level in SILENCE_LOGS.items()]
    return _config


def set_log_name(name: str) -> None:
    for handler in getLogger().handlers:
        handler.setFormatter(
            Formatter(
                f"[{name}] (%(asctime)s) %(levelname)s: %(message)s",
                datefmt=LOG_DATE_FORMAT,
            )
        )
