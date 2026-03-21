import os

import streamlit as st
from RestrictedPython import compile_restricted
from RestrictedPython.transformer import RestrictingNodeTransformer
from streamlit_monaco import st_monaco


class StrategyPolicy(RestrictingNodeTransformer):
    # Allow type annotations (dataclass fields, function signatures, etc.)
    def visit_AnnAssign(self, node):
        return self.node_contents_visit(node)


def validate_strategy(code: str) -> str | None:
    """Returns an error string if code is unsafe/invalid, else None."""
    try:
        compile_restricted(code, filename="<strategy>", mode="exec", policy=StrategyPolicy)
    except SyntaxError as e:
        return f"Syntax error: {e}"
    except Exception as e:
        return f"Validation error: {e}"
    return None


# -------------------------
# CONFIG
# -------------------------
DATA_DIR = "strategy_files"
os.makedirs(DATA_DIR, exist_ok=True)

st.set_page_config(layout="wide")
st.title("Strategy File Viewer + Editor")

# -------------------------
# FILE LIST (VIEW ONLY)
# -------------------------
st.header("📂 Existing Strategy Files")

files = [f for f in os.listdir(DATA_DIR) if f.endswith(".py")]

selected_file = st.selectbox("Select a file to view", ["-- Select --"] + sorted(files))

if selected_file != "-- Select --":
    path = os.path.join(DATA_DIR, selected_file)
    with open(path, "r") as f:
        content = f.read()

    st.subheader(f"Viewing: {selected_file}")
    st.code(content, language="python")  # read-only view

# -------------------------
# NEW FILE CREATION
# -------------------------
st.header("➕ Create New Strategy File")

file_name = st.text_input("New file name (no extension)")

default_code = """from dataclasses import dataclass

@dataclass
class TradeConfig:
    symbol: str
    entry_price: float
    stop_loss: float

def run_strategy(config: TradeConfig):
    print(f"Trading {config.symbol} at {config.entry_price}")
"""


autocomplete_js = """
monaco.languages.registerCompletionItemProvider('python', {
    provideCompletionItems: function(model, position) {
        return {
            suggestions: [
                {
                    label: 'TradeConfig',
                    kind: monaco.languages.CompletionItemKind.Class,
                    insertText: 'TradeConfig',
                    documentation: 'Dataclass for trade configuration'
                },
                {
                    label: 'symbol',
                    kind: monaco.languages.CompletionItemKind.Field,
                    insertText: 'symbol=',
                },
                {
                    label: 'entry_price',
                    kind: monaco.languages.CompletionItemKind.Field,
                    insertText: 'entry_price=',
                },
                {
                    label: 'stop_loss',
                    kind: monaco.languages.CompletionItemKind.Field,
                    insertText: 'stop_loss=',
                },
                {
                    label: 'run_strategy',
                    kind: monaco.languages.CompletionItemKind.Function,
                    insertText: 'run_strategy(config)',
                }
            ]
        };
    }
});
"""

st.subheader("Editor")

code = st_monaco(
    value=default_code,
    language="python",
    theme="vs-dark",
    height="500px",
)

# Inject autocomplete JS (hacky but works in many builds)
st.components.v1.html(
    f"""
    <script>
    {autocomplete_js}
    </script>
    """,
    height=0,
)

# -------------------------
# SAVE LOGIC (WRITE ONCE)
# -------------------------
if st.button("💾 Save New File (Locked)"):
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

                st.success(f"Saved {full_name} ✅ (read-only after this)")
