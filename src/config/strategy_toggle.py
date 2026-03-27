from dataclasses import dataclass

from src.utils.strategy_toggle import StrategyToggle

"""
Hard-coded configuration for what type of strategy toggles exist. These values are not generally
configurable because changing them would require updating the streamlit UI (and other logic).
"""


@dataclass
class _StrategyToggleConfig:
    livetest: StrategyToggle
    trading: StrategyToggle


class StrategyToggleConfigProvider:

    _instance = None

    @classmethod
    def get(cls) -> "_StrategyToggleConfig":
        if cls._instance is None:
            cls._instance = _StrategyToggleConfig(
                livetest=StrategyToggle("livetest"),
                trading=StrategyToggle("trading"),
            )
        return cls._instance
