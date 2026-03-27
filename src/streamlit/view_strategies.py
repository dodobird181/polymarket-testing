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
            label = "✅ Enabled" if toggles.livetest.is_enabled(filename) else "❌ Disabled"
            if st.button(label, key=f"toggle_enabled_{filename}"):
                toggles.livetest.toggle(filename)
                st.rerun()
        with col_trading:
            label = "✅ Strategy is TRADING" if toggles.trading.is_enabled(filename) else "❌ Disabled"
            if st.button(label, key=f"toggle_live_{filename}"):
                toggles.trading.toggle(filename)
                st.rerun()

    selected_file = st.session_state.selected_file
    if selected_file:
        path = Path(config.strategy.file_dir).joinpath(selected_file)
        with open(path, "r") as fh:
            content = fh.read()
        st.subheader(f"Viewing: {selected_file}")

        plot_path = Path(config.strategy.plot_dir) / selected_file.replace(".py", ".png")
        if plot_path.exists():
            st.image(str(plot_path), width=1000)
        else:
            st.info("Plot data not available yet. Please enable the strategy and come back in 10 minutes...")

        st.code(content, language="python")
