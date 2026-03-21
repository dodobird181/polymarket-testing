import os

import streamlit as st
from streamlit_monaco import st_monaco

from strategy_editor_utils import DATA_DIR, validate_strategy

st.set_page_config(layout="wide")
st.title("Add strategy")

file_name = st.text_input("File name (no extension)")

default_code = """from dataclasses import dataclass

@dataclass
class TradeConfig:
    symbol: str
    entry_price: float
    stop_loss: float

def run_strategy(config: TradeConfig):
    print(f"Trading {config.symbol} at {config.entry_price}")
"""

code = st_monaco(
    value=default_code,
    language="python",
    theme="vs-dark",
    height="500px",
)

if st.button("💾 Save (Locked)"):
    if not file_name.strip():
        st.error("Please enter a file name")
    else:
        err = validate_strategy(code)
        if err:
            st.error(f"Strategy rejected: {err}")
        else:
            full_name = f"{file_name}.py"
            path = os.path.join(DATA_DIR, full_name)
            if os.path.exists(path):
                st.error("File already exists ❌")
            else:
                with open(path, "w") as f:
                    f.write(code)
                st.success(f"Saved {full_name} ✅")
