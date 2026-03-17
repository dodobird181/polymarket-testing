from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Market:
    """A single resolved BTC 5-min up/down market."""
    slug: str                        # e.g. btc-updown-5m-1773708600
    condition_id: str                # 0x-prefixed hex, used for trades
    up_token_id: str                 # CLOB token ID for the "Up" outcome
    down_token_id: str               # CLOB token ID for the "Down" outcome
    title: str                       # "Bitcoin Up or Down - March 16, 8:50PM-8:55PM ET"
    start_time: datetime             # window open (eventStartTime)
    end_time: datetime               # window close (endDate)
    closed: bool
    resolved: bool                   # True once outcome prices are 0/1
    outcome: Optional[str]           # "Up", "Down", or None if still open
    up_price_at_close: float         # outcomePrices[0] after resolution
    volume: float                    # total $ traded


@dataclass
class PricePoint:
    """A single (timestamp, price) from the CLOB price-history endpoint."""
    t: int    # unix timestamp
    p: float  # price of the Up token (0–1)


@dataclass
class MarketWithHistory:
    """Market metadata combined with its intra-window price series."""
    market: Market
    history: list[PricePoint] = field(default_factory=list)

    @property
    def open_price(self) -> Optional[float]:
        return self.history[0].p if self.history else None

    @property
    def close_price(self) -> Optional[float]:
        return self.history[-1].p if self.history else None

    @property
    def max_price(self) -> Optional[float]:
        return max(h.p for h in self.history) if self.history else None

    @property
    def min_price(self) -> Optional[float]:
        return min(h.p for h in self.history) if self.history else None
