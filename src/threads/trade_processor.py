from pathlib import Path
from sys import path as systempath

systempath.insert(0, str(Path(__file__).parents[2]))
from src.config import getLogger, load_config
from src.utils.redis import mark_done, wait_for_trade_to_process

"""
Trade processor scans a redis queue for incoming trades and broadcasts them to Polymarket.
Failed trades remain in queue:processing for manual recovery.
"""

logger = getLogger(__name__)

if __name__ == "__main__":
    load_config()

    while True:
        processing_trade = wait_for_trade_to_process()
        try:
            # TODO: broadcast trade to Polymarket via src/trade/broadcast.py
            logger.info(
                "Processing trade %s: %s",
                processing_trade.pending_trade.trade.id,
                processing_trade.pending_trade.trade.display_str(),
            )
            mark_done(processing_trade)
            logger.info("Done trade %s", processing_trade.pending_trade.trade.id)
        except Exception as e:
            logger.error("Failed to process trade %s: %s", processing_trade.pending_trade.trade.id, e)
