from os import listdir
from pathlib import Path

import streamlit as st

from strategy_file_toggle import STRATEGY_FILES_DIR, livetest_toggle, trading_toggle

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
