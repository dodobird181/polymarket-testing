from pathlib import Path

from log_config import getLogger
from strategy_editor_utils import STRATEGY_FILES_DIR

logger = getLogger(__name__)


class StrategyFileToggle:
    """
    Represents a toggle-button in the UI for enabling / disabling a certain
    type of strategy-file behaviour.
    """

    def __init__(self, dirname: str):
        # dirname is the name of the directory inside the STRATEGY_FILES_DIR
        # that we want to *use* to keep track of what state the toggle is in.
        self.dirname = dirname
        self.dir = Path(STRATEGY_FILES_DIR) / self.dirname
        self.dir.mkdir(exist_ok=True)

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
            logger.info("Enabled '%s' behaviour for strategy '%s'.", self.dirname, filename)
            return False
        else:
            path.touch()
            logger.info("Disabled '%s' behaviour for strategy '%s'.", self.dirname, filename)
            return True


livetest_toggle = StrategyFileToggle("is_livetesting")
trading_toggle = StrategyFileToggle("is_trading")
