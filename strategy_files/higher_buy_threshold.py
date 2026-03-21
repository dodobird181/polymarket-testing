from dataclasses import dataclass

@dataclass
class TradeConfig:
    symbol: str
    entry_price: float
    stop_loss: float

def run_strategy(config: TradeConfig):
    print(f"Trading {config.symbol} at {config.entry_price}")
