import os
import subprocess
from pathlib import Path
from time import sleep

from log_config import getLogger
from market_info import current_window_start, elapsed

logger = getLogger(__name__)

ENABLED_DIR = Path(__file__).parent / "strategy_files" / "enabled"

ALWAYS_PRESENT = {
    "plot_watcher": ["poetry", "run", "python", "plot_watcher.py", "strategy_logs"],
    "streamlit_app": ["poetry", "run", "streamlit", "run", "app.py", "--server.headless", "true"],
}

env = {**os.environ, "PYTHONUNBUFFERED": "1"}
running: dict[str, subprocess.Popen] = {}


def start(name: str, cmd: list[str]):
    running[name] = subprocess.Popen(cmd, env=env)
    logger.info("Started %s (pid=%d)", name, running[name].pid)


def strategy_cmd(name: str) -> list[str]:
    return [
        "poetry",
        "run",
        "python",
        "live_monitor.py",
        f"strategy_logs/{name}.jsonl",
        f"strategy_files/{name}.py",
    ]


def start_new_strategies():
    enabled = {f.stem for f in ENABLED_DIR.glob("*.enabled")}
    for name in sorted(enabled - running.keys()):
        start(name, strategy_cmd(name))


if __name__ == "__main__":
    for name, cmd in ALWAYS_PRESENT.items():
        start(name, cmd)

    start_new_strategies()

    ready = True
    while True:
        start_ts = current_window_start()
        window_seconds = elapsed(start_ts)
        logger.debug("Seconds: %s", window_seconds)
        if window_seconds == 0 and ready:
            ready = False
            start_new_strategies()
        if window_seconds == 280:
            ready = True
        sleep(0.5)
