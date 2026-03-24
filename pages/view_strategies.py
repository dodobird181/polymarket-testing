from os import listdir
from pathlib import Path

import streamlit as st

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


st.set_page_config(layout="wide")
st.title("List of all strategies")

files = sorted(f for f in listdir(STRATEGY_FILES_DIR) if f.endswith(".py"))

if not files:
    st.info("No strategy files yet.")
else:
    if "selected_file" not in st.session_state:
        st.session_state.selected_file = None

    _, col_above_toggles = st.columns([3, 4])
    with col_above_toggles:
        st.markdown(
            "**NOTE**: toggling behaviour will _only_ take effect at the start of the next 5-min market window."
        )

    for filename in files:
        col_name, col_above_toggles, col_trading = st.columns([3, 2, 2])
        with col_name:
            btn_type = "primary" if filename == st.session_state.selected_file else "secondary"
            st.button(
                filename,
                key=f"view_strategy_button_{filename}",
                type=btn_type,
                on_click=lambda name=filename: st.session_state.update(selected_file=name),
            )
        with col_above_toggles:
            label = "✅ Enabled" if livetest_toggle.is_enabled(filename) else "❌ Disabled"
            if st.button(label, key=f"toggle_enabled_{filename}"):
                livetest_toggle.toggle(filename)
                st.rerun()
        with col_trading:
            label = "✅ Strategy is TRADING" if trading_toggle.is_enabled(filename) else "❌ Disabled"
            if st.button(label, key=f"toggle_live_{filename}"):
                trading_toggle.toggle(filename)
                st.rerun()

    selected_file = st.session_state.selected_file
    if selected_file:
        path = Path(STRATEGY_FILES_DIR).joinpath(selected_file)
        with open(path, "r") as fh:
            content = fh.read()
        st.subheader(f"Viewing: {selected_file}")

        plot_path = Path("strategy_plots") / selected_file.replace(".py", ".png")
        if plot_path.exists():
            st.image(str(plot_path), width=1000)
        else:
            st.info("Plot data not available yet. Please enable the strategy and come back in 10 minutes...")

        st.code(content, language="python")
        st.code(content, language="python")
        st.code(content, language="python")
