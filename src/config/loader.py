from dataclasses import dataclass
from logging import INFO, WARNING, _nameToLevel, basicConfig, getLogger
from os import environ

from dotenv import load_dotenv

DEFAULT_LOG_LEVEL = INFO
DEFAULT_STRATEGY_FILE_DIR = "data/strategy"
DEFAULT_STRATEGY_LOG_DIR = "data/logs"
DEFAULT_STRATEGY_PLOT_DIR = "data/plots"


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

    polymarket: Polymarket
    strategy: Strategy

    redis_url: str
    log_level: int


_config = None


def load_config() -> Config:
    global _config
    if _config is None:
        load_dotenv()
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
            redis_url=environ["REDIS_URL"],
            log_level=_resolve_log_level_from_environ(),
        )
        basicConfig(
            level=_config.log_level,
            format="[%(asctime)s] %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d @ %I:%M:%S %p %Z",
        )
        [getLogger(module).setLevel(level) for module, level in SILENCE_LOGS.items()]
        logger = getLogger(__name__)
        logger.info("Loaded config.")
    return _config
