import os

from RestrictedPython import compile_restricted
from RestrictedPython.transformer import RestrictingNodeTransformer

DATA_DIR = "strategy_files"
os.makedirs(DATA_DIR, exist_ok=True)


class StrategyPolicy(RestrictingNodeTransformer):
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
