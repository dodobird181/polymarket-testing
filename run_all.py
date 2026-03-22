import os
import subprocess
import sys
import threading
from pathlib import Path
from time import sleep

from log_config import getLogger
from market_info import current_window_start, elapsed

logger = getLogger(__name__)

ENABLED_DIR = Path(__file__).parent / "strategy_files" / "enabled"

ALWAYS_PRESENT = {
    "plot_watcher": ["poetry", "run", "python", "plot_watcher.py", "strategy_logs"],
    "streamlit_app": [
        "poetry",
        "run",
        "streamlit",
        "run",
        "app.py",
        "--server.headless",
        "true",
        "--server.baseUrlPath",
        "polymarket",
    ],
}

env = {**os.environ, "PYTHONUNBUFFERED": "1"}
running: dict[str, subprocess.Popen] = {}


def _pipe_reader(name: str, stream):
    for line in stream:
        sys.stdout.write(f"[{name}] {line}")
        sys.stdout.flush()


def start(name: str, cmd: list[str]):
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    running[name] = proc
    threading.Thread(target=_pipe_reader, args=(name, proc.stdout), daemon=True).start()
    logger.info("Started %s (pid=%d)", name, proc.pid)


def strategy_cmd(name: str) -> list[str]:
    return [
        "poetry",
        "run",
        "python",
        "live_monitor.py",
        f"strategy_logs/{name}.jsonl",
        f"strategy_files/{name}.py",
    ]


def stop_strategy(name: str):
    proc = running.pop(name)
    proc.terminate()
    logger.info("Stopped %s (pid=%d) because it was disabled.", name, proc.pid)


def sync_strategies():
    enabled = {f.stem for f in ENABLED_DIR.glob("*.enabled")}
    strategy_names = running.keys() - ALWAYS_PRESENT.keys()
    for name in sorted(enabled - running.keys()):
        start(name, strategy_cmd(name))
    for name in sorted(strategy_names - enabled):
        stop_strategy(name)


if __name__ == "__main__":

    for name, cmd in ALWAYS_PRESENT.items():
        start(name, cmd)

    sync_strategies()

    ready = True
    while True:
        start_ts = current_window_start()
        window_seconds = elapsed(start_ts)
        if window_seconds == 0 and ready:
            ready = False
            sync_strategies()
        if window_seconds == 280:
            ready = True
        sleep(0.5)
