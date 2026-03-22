from pathlib import Path
from sys import argv
from time import sleep

from log_config import getLogger
from market_info import current_window_start, elapsed
from plot import plot

"""
Regenerates the plots in "strategy_plots/" every 5 minutes.
"""

logger = getLogger(__name__)

if __name__ == "__main__":

    if len(argv) == 2:
        LOG_DIRNAME = argv[1]
    else:
        raise ValueError("Usage: python plot_watcher.py <log_dirname>")

    logger.info("Watching '%s' for logfiles to plot...", LOG_DIRNAME)

    # additional variable to make sure we only re-calculate the plots ONCE ever 5 mins,
    # even though we poll more than once per second.
    ready = True
    while True:
        start_ts = current_window_start()
        window_seconds = elapsed(start_ts)
        logger.debug("Seconds: %s", window_seconds)
        if window_seconds == 0 and ready == True:
            ready = False
            filepaths = [f.name for f in Path(LOG_DIRNAME).iterdir()]
            logger.debug("Plot watcher found %s to plot.", filepaths)
            for filepath in filepaths:
                plot(
                    logfile=str(Path(LOG_DIRNAME, filepath)),
                    savefile="strategy_plots/{filename}.png".format(filename=filepath.split(".")[0]),
                    show=False,
                )
        if window_seconds == 280:
            # reset "ready" near the end of the window
            ready = True
        sleep(0.5)
