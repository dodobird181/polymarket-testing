from json import dumps
from pathlib import Path
from sys import path as systempath

systempath.insert(0, str(Path(__file__).parents[2]))
from src.config import StrategyToggleConfigProvider, getLogger, load_config
from src.trade import broadcast_trade
from src.utils import (
    CompletedTrade,
    ProcessingTrade,
    mark_completed,
    wait_for_trade_to_process,
)

"""
Scans a redis queue for incoming trades and broadcasts them to Polymarket. Failed trades
remain in the processing queue for manual recovery.
"""

logger = getLogger(__name__)
config = load_config()
toggles = StrategyToggleConfigProvider().get()


def _trade_logpath(processing_trade: ProcessingTrade) -> Path | None:
    """
    The logpath to log this trade under.
    """
    if toggles.trading.is_enabled(processing_trade.strategy_name):
        file_prefix = "trading."
    elif toggles.livetest.is_enabled(processing_trade.strategy_name):
        file_prefix = "live_testing."
    else:
        logger.warning(
            "Returning 'None' as trade logpath for '%s', because neither trading, nor live-testing are enabled for that strategy.",
            processing_trade.strategy_name,
        )
        return None
    filename = f"{file_prefix}{processing_trade.strategy_name}.jsonl"
    return Path(config.strategy.log_dir) / filename


def _log_trade(trade: CompletedTrade) -> None:
    """
    Log the trade if it's strategy is currently trading or live-testing. Otherwise, do nothing.
    """
    if logpath := _trade_logpath(trade):
        logpath.parent.mkdir(exist_ok=True, parents=True)
        with open(logpath, "a") as logfile:
            logfile.write(dumps(trade.to_dict()) + "\n")


if __name__ == "__main__":
    logger.info("Started trade processor!")
    while True:
        trade = wait_for_trade_to_process()
        try:
            logger.info(
                "Processing trade '%s' for strategy '%s': %s.",
                trade.id[:4],
                trade.strategy_name,
                trade.display_str(),
            )
            try:
                if toggles.trading.is_enabled(trade.strategy_name) is True:
                    broadcast_trade(trade)
                completed_trade = mark_completed(trade)
                _log_trade(completed_trade)
                logger.info("Successfully processed trade %s.", trade.id)
            except Exception as e:
                logger.error("Error broadcasting trade for strategy %s.", trade.strategy_name, exc_info=e)
        except Exception as e:
            logger.error("Failed to process trade %s: %s", trade.id, e)
