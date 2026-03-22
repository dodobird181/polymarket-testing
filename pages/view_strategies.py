import os
from pathlib import Path

import streamlit as st

from strategy_editor_utils import DATA_DIR

ENABLED_DIR = Path(DATA_DIR) / "enabled"
ENABLED_DIR.mkdir(exist_ok=True)


def enabled_path(filename: str) -> Path:
    return ENABLED_DIR / filename.replace(".py", ".enabled")


def is_enabled(filename: str) -> bool:
    return enabled_path(filename).exists()


def toggle_enabled(filename: str):
    p = enabled_path(filename)
    if p.exists():
        p.unlink()
    else:
        p.touch()


st.set_page_config(layout="wide")
st.title("Strategies")
st.write("NOTE: Enabling and disabling strategies will only take effect during the next 5-minute window.")

files = sorted(f for f in os.listdir(DATA_DIR) if f.endswith(".py"))

if not files:
    st.info("No strategy files yet.")
else:
    if "selected_file" not in st.session_state:
        st.session_state.selected_file = None

    for f in files:
        col_name, col_toggle = st.columns([6, 1])
        with col_name:
            btn_type = "primary" if f == st.session_state.selected_file else "secondary"
            st.button(
                f,
                key=f"file_{f}",
                type=btn_type,
                on_click=lambda name=f: st.session_state.update(selected_file=name),
            )
        with col_toggle:
            enabled = is_enabled(f)
            label = "✅ Enabled" if enabled else "❌ Disabled"
            if st.button(label, key=f"toggle_{f}"):
                toggle_enabled(f)
                st.rerun()

    selected_file = st.session_state.selected_file
    if selected_file:
        path = os.path.join(DATA_DIR, selected_file)
        with open(path, "r") as fh:
            content = fh.read()
        st.subheader(f"Viewing: {selected_file}")
        st.code(content, language="python")

        plot_path = Path("strategy_plots") / selected_file.replace(".py", ".png")
        if plot_path.exists():
            st.image(str(plot_path))
        else:
            st.info("Plot data not available yet. Please enable the strategy and come back in 10 minutes...")
