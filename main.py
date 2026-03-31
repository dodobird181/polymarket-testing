from dataclasses import dataclass
from os import environ
from subprocess import PIPE, STDOUT, Popen
from sys import stdout
from threading import Thread
from time import sleep

from src.config import (
    StrategyToggleConfigProvider,
    getLogger,
    load_config,
    set_log_name,
)
from src.utils import StrategyToggle, current_window_start, elapsed

logger = getLogger(__name__)
config = load_config()


@dataclass
class _ProcessDef:
    name: str
    command: list[str]


CORE_PROCESSES = [
    # regenerate PNG plot images when strategy logs change
    _ProcessDef(
        name="plot_watcher",
        command=["poetry", "run", "python", "src/threads/plot_watcher.py"],
    ),
    # fetch live and historical BTC price data and save to redis
    _ProcessDef(
        name="kraken_fetcher",
        command=["poetry", "run", "python", "src/threads/kraken_fetcher.py"],
    ),
    # execute realtime trades on Polymarket
    _ProcessDef(
        name="trade_processor",
        command=["poetry", "run", "python", "src/threads/trade_processor.py"],
    ),
    # webapp for viewing, creating, and toggling strategies
    _ProcessDef(
        name="streamlit_app",
        command=[
            "poetry",
            "run",
            "streamlit",
            "run",
            "src/threads/dashboard.py",
            "--server.headless",
            "true",
            "--server.baseUrlPath",
            "polymarket",
        ],
    ),
]


class _Strategy:

    def __init__(self, name: str):
        self.pdef = _ProcessDef(
            name=name,
            command=[
                "poetry",
                "run",
                "python",
                "src/threads/live_monitor.py",
                f"{config.strategy.log_dir}/{name}.jsonl",
                f"{config.strategy.file_dir}/{name}.py",
            ],
        )
        self._process: Popen | None = None

    def start(self) -> Popen:
        self._process = start(self)
        return self._process

    def pid(self) -> int | None:
        if self._process is not None:
            return self._process.pid
        return None

    def is_running(self) -> bool:
        return self._process is not None

    def stop(self) -> bool:
        if self._process is not None:
            self._process.terminate()
            self._process = None
            return True
        return False


class _StrategyBook:
    """
    A strategy book is a place to keep stratagies in memory. Each strategy stores
    a reference to it's process, which is needed to disable it.
    """

    def __init__(self, name: str):
        self.name = name
        self._book = {}

    def add(self, strategy: _Strategy) -> None:
        self._book[strategy.pdef.name] = strategy

    def contains(self, name: str) -> bool:
        return name in self._book

    def cross_off(self, name: str) -> bool:
        if self.contains(name):
            self._book.pop(name)
            return True
        return False

    def as_list(self) -> list[_Strategy]:
        return [x for x in self._book.values()]


def _pipe_reader(name, stream):
    for line in stream:
        stdout.write(f"[{name}] {line}")
        stdout.flush()


def __strategy_pipe_reader(name, stream):
    for line in stream:
        # just add a prefix in the logs for all strategy processes
        stdout.write(f"<< STRATEGY >> [{name}] {line}")
        stdout.flush()


def start(obj: _ProcessDef | _Strategy) -> Popen:
    """
    Start a process in a new thread.
    """

    # resolve the process definition and pipe reader
    pdef = obj.pdef if isinstance(obj, _Strategy) else obj
    pipe_reader = __strategy_pipe_reader if isinstance(obj, _Strategy) else _pipe_reader

    # start the process
    env = {**environ, "PYTHONUNBUFFERED": "1"}
    process = Popen(pdef.command, env=env, stdout=PIPE, stderr=STDOUT, text=True)
    thread = Thread(target=pipe_reader, args=(pdef.name, process.stdout), daemon=True)
    thread.name = pdef.name
    thread.start()
    return process


def sync_strategies(book: _StrategyBook, toggle: StrategyToggle):
    """
    Start strategies that are toggled "on", stop strategies that are toggled "off", and
    add or remove them from the given strategy book, respectively.
    """
    enabled = {path.stem for path in toggle.dir.glob("*")}

    for name in sorted(enabled):
        if not book.contains(name):
            strategy = _Strategy(name)
            process = strategy.start()
            book.add(strategy)
            logger.info("Started strategy %s (pid=%d).", name, process.pid)

    for strategy in book.as_list():
        name = strategy.pdef.name
        if name not in enabled:
            logger.info("Stopping %s (pid=%d), because it was removed from '%s'.", name, strategy.pid, book.name)
            strategy.stop()
            book.cross_off(name)

    logger.info(
        "Synced '%s' strategies. Currently running are: %s",
        book.name,
        str([x.pdef.name for x in book.as_list()]),
    )


if __name__ == "__main__":

    set_log_name("main")
    logger.info("Starting up core processes: %s.", str([x.name for x in CORE_PROCESSES]))
    for pdef in CORE_PROCESSES:
        process = start(pdef)
        logger.info("Started core process %s (pid=%d).", pdef.name, process.pid)

    logger.info("Starting strategies enabled for live-testing...")
    toggles = StrategyToggleConfigProvider().get()
    livetesting_book = _StrategyBook("live-testing")
    sync_strategies(livetesting_book, toggles.livetest)

    ready = True
    while True:
        start_ts = current_window_start()
        window_seconds = elapsed(start_ts)
        if window_seconds == 0 and ready:
            ready = False
            # sync every 5 mins
            sync_strategies(livetesting_book, toggles.livetest)
        if window_seconds == 280:
            ready = True
        sleep(0.5)
