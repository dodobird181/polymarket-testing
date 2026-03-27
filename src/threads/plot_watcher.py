from pathlib import Path
from time import sleep

from src.config import getLogger, load_config
from src.utils.market_info import current_window_start, elapsed
from src.utils.plot_logfile import plot_logfile

"""
Regenerates plot PNG images from strategy logfiles every 5 mins, at the start of the BTC 5-min market window.
"""

logger = getLogger(__name__)
config = load_config()

if __name__ == "__main__":

    logger.info("Watching '%s' for logfiles to plot...", config.strategy.log_dir)

    # additional variable to make sure we only re-calculate the plots ONCE ever 5 mins,
    # even though we poll more than once per second.
    ready = True
    while True:
        start_ts = current_window_start()
        window_seconds = elapsed(start_ts)
        logger.debug("Seconds: %s", window_seconds)
        if window_seconds == 0 and ready == True:
            ready = False
            logfiles = [f for f in Path(config.strategy.log_dir).iterdir() if f.suffix == ".jsonl"]
            logger.debug("Plot watcher found %s to plot.", logfiles)
            for logfile in logfiles:
                plot_logfile(
                    logfile=str(logfile),
                    savefile=f"strategy_plots/{logfile.stem}.png",
                    show=False,
                )
        if window_seconds == 280:
            # reset "ready" near the end of the window
            ready = True
        sleep(0.5)
