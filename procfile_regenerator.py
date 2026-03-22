from os import getpid, kill
from pathlib import Path
from signal import SIGTERM
from time import sleep

import psutil

from log_config import getLogger
from market_info import current_window_start, elapsed

logger = getLogger(__name__)

PROCFILE = Path(__file__).parent / "Procfile"
ENABLED_DIR = Path(__file__).parent / "strategy_files" / "enabled"

ALWAYS_PRESENT = [
    "plot_watcher: PYTHONUNBUFFERED=1 poetry run python plot_watcher.py strategy_logs",
    "procfile_regenerator: PYTHONUNBUFFERED=1 poetry run python procfile_regenerator.py",
    "streamlit_app: PYTHONUNBUFFERED=1 poetry run streamlit run app.py --server.headless true",
]


def regenerate_procfile():
    lines = []
    for enabled_file in ENABLED_DIR.glob("*.enabled"):
        name = enabled_file.stem
        lines.append(
            f"{name}: PYTHONUNBUFFERED=1 poetry run python live_monitor.py"
            f" strategy_logs/{name}.jsonl strategy_files/{name}.py"
        )
    lines.extend(ALWAYS_PRESENT)
    PROCFILE.write_text("\n".join(lines) + "\n")
    logger.info("Wrote Procfile with %d strategy line(s)", len(lines) - len(ALWAYS_PRESENT))


def find_honcho_pid():
    """
    Walk up process tree to find the honcho parent.
    """
    proc = psutil.Process(getpid())
    while True:
        parent = proc.parent()
        if parent is None or parent.pid == 0:
            return None
        cmdline = " ".join(parent.cmdline())
        if "honcho" in cmdline or parent.name() == "honcho":
            return parent.pid
        proc = parent


if __name__ == "__main__":

    ready = True
    while True:
        start_ts = current_window_start()
        window_seconds = elapsed(start_ts)
        logger.debug("Seconds: %s", window_seconds)
        if window_seconds == 0 and ready == True:
            ready = False
            logger.info("Regenerating procfile...")
            regenerate_procfile()
            logger.info("Restarting honcho process...")
            honcho_pid = find_honcho_pid()
            if honcho_pid:
                # kill the honcho process, but because we assume that the process was started with `run.sh`
                # it should come back online after a second or so...
                kill(honcho_pid, SIGTERM)
                exit(0)
            else:
                logger.error("Could not find honcho process to kill!")
                exit(1)
        if window_seconds == 280:
            # reset "ready" near the end of the window
            ready = True
        sleep(0.5)
