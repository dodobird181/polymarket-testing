from os import listdir
from pathlib import Path

import streamlit as st
from src.config import StrategyToggleConfigProvider, load_config

config = load_config()
toggles = StrategyToggleConfigProvider.get()

st.title("List of all strategies")

Path(config.strategy.file_dir).mkdir(exist_ok=True)
files = sorted(f for f in listdir(config.strategy.file_dir) if f.endswith(".py"))

if not files:
    st.info("No strategy files yet.")
else:
    if "selected_file" not in st.session_state:
        st.session_state.selected_file = None

    # headers and note above the toggle columns
    col_name, col_livetest, col_trading = st.columns([3, 2, 2])
    with col_livetest:
        st.header("Toggle Live-testing")
    with col_trading:
        st.header("Toggle Trading")
    _, col_above_toggles = st.columns([3, 4])
    with col_above_toggles:
        st.markdown(
            "**NOTE**: toggling behaviour will _only_ take effect at the start of the next 5-min market window."
        )

    # render each file's row and toggles
    for filename in files:
        col_name, col_livetest, col_trading = st.columns([3, 2, 2])
        with col_name:
            btn_type = "primary" if filename == st.session_state.selected_file else "secondary"
            st.button(
                filename,
                key=f"view_strategy_button_{filename}",
                type=btn_type,
                on_click=lambda name=filename: st.session_state.update(selected_file=name),
            )
        with col_livetest:
            label = "✅ Enabled" if toggles.livetest.is_enabled(filename) else "❌ Disabled"
            if st.button(label, key=f"toggle_enabled_{filename}"):
                toggles.livetest.toggle(filename)
                st.rerun()
        with col_trading:
            label = "✅ Strategy is TRADING" if toggles.trading.is_enabled(filename) else "❌ Disabled"
            if st.button(label, key=f"toggle_live_{filename}"):
                toggles.trading.toggle(filename)
                st.rerun()

    # render the selected file's plot and strategy code
    selected_file = st.session_state.selected_file
    if selected_file:
        path = Path(config.strategy.file_dir).joinpath(selected_file)
        with open(path, "r") as fh:
            content = fh.read()
        st.subheader(f"Viewing: {selected_file}")

        stem = selected_file.replace(".py", "")
        plot_dir = Path(config.strategy.plot_dir)
        plots = [
            ("Trading", plot_dir / f"trading.{stem}.png"),
            ("Live-testing", plot_dir / f"live_testing.{stem}.png"),
        ]
        shown = [(label, p) for label, p in plots if p.exists()]
        if shown:
            for label, p in shown:
                st.caption(label)
                st.image(str(p), width=1000)
        else:
            st.info("Plot data not available yet. Please enable the strategy and come back in 10 minutes...")

        st.code(content, language="python")
