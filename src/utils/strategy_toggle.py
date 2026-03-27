from pathlib import Path

from src.config import getLogger, load_config

logger = getLogger(__name__)
config = load_config()


class StrategyToggle:
    """
    File-based persistance for boolean options related to a strategy.
    """

    def __init__(self, dirname: str):
        # dirname is the name of the directory inside the strategy file dir
        # that we want to *use* to keep track of what state the toggle is in.
        self.dirname = dirname
        self.dir = Path(config.strategy.file_dir) / self.dirname
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, filename: str) -> Path:
        return self.dir / filename.replace(".py", "")

    def is_enabled(self, filename: str) -> bool:
        return self._path(filename).exists()

    def toggle(self, filename: str) -> bool:
        """
        Returns `True` if the toggle was enabled for the given strategy filename, or `False` if it was disabled.
        """
        path = self._path(filename)
        if path.exists():
            path.unlink()
            logger.info("Disabled '%s' behaviour for strategy '%s'.", self.dirname, filename)
            return False
        else:
            path.touch()
            logger.info("Enabled '%s' behaviour for strategy '%s'.", self.dirname, filename)
            return True
