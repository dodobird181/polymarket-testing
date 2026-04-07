from json import loads
from pathlib import Path
from time import time

from src.config import getLogger, load_config
from src.utils.market_info import Btc5MinMarketOutcome, get_market_outcome_from_slug
from src.utils.redis.polymarket import cache_outcome, get_cached_outcome

logger = getLogger(__name__)
config = load_config()


def _fetch_outcome(slug: str, cache: dict) -> str | None:
    if slug in cache:
        return cache[slug]
    try:
        cached = get_cached_outcome(slug)
        if cached is not None and cached != Btc5MinMarketOutcome.UNRESOLVED:
            cache[slug] = cached.value
            return cached.value
    except Exception:
        pass
    try:
        outcome = get_market_outcome_from_slug(slug)
        if outcome != Btc5MinMarketOutcome.UNRESOLVED:
            cache[slug] = outcome.value
            try:
                cache_outcome(slug, outcome)
            except Exception:
                pass
            return outcome.value
    except Exception:
        pass
    return None


def check(
    strategy_name: str,
    window_hours: float = 8,
    min_trades: int = 5,
    min_win_rate: float = 0.60,
) -> bool:
    """
    Returns True if the circuit breaker should trip for the given strategy.

    Reads the strategy's trading log, fetches market outcomes for trades within
    the last `window_hours` hours, and trips if the win rate drops below
    `min_win_rate`. Requires at least `min_trades` resolved trades in the window
    before it can trip.
    """
    logfile = Path(config.strategy.log_dir) / f"trading.{strategy_name}.jsonl"
    if not logfile.exists():
        return False

    cutoff = time() - window_hours * 3600
    outcome_cache: dict[str, str] = {}
    wins = losses = 0

    try:
        with logfile.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = loads(line)
                if record.get("enqueued_at", 0) < cutoff:
                    continue
                market_outcome = _fetch_outcome(record["state"]["slug"], outcome_cache)
                if market_outcome is None:
                    continue
                outcome_matches = record["outcome"] == market_outcome
                is_buy = record.get("side", "buy") == "buy"
                is_win = outcome_matches if is_buy else not outcome_matches
                if is_win:
                    wins += 1
                else:
                    losses += 1
    except Exception as e:
        logger.warning("Circuit breaker could not read log for '%s': %s", strategy_name, e)
        return False

    total = wins + losses
    if total < min_trades:
        return False

    win_rate = wins / total
    if win_rate < min_win_rate:
        logger.warning(
            "Circuit breaker tripped for '%s': win rate %.0f%% (%d/%d) over last %.0fh is below threshold %.0f%%.",
            strategy_name,
            win_rate * 100,
            wins,
            total,
            window_hours,
            min_win_rate * 100,
        )
        return True

    return False
