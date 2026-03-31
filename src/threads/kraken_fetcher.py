from pathlib import Path
from sys import path as systempath
from time import sleep

systempath.insert(0, str(Path(__file__).parents[2]))
from src.config import getLogger, load_config
from src.kraken import KrakenData, fetch_history, fetch_live_price, fetch_price_at
from src.utils import current_window_start
from src.utils.redis import set_kraken_data

logger = getLogger(__name__)


if __name__ == "__main__":
    config = load_config()

    last_window_ts: int | None = None
    history: list[KrakenData.Candle] = []
    window_start_price: float | None = None

    while True:
        try:
            start_ts = current_window_start()
            if start_ts != last_window_ts:
                raw_candles = fetch_history()
                history = [
                    KrakenData.Candle(
                        open_time=k[0],
                        open=float(k[1]),
                        high=float(k[2]),
                        low=float(k[3]),
                        close=float(k[4]),
                        vwap=float(k[5]),
                        volume=float(k[6]),
                        trade_count=k[7],
                    )
                    for k in raw_candles
                ]
                window_start_price = fetch_price_at(start_ts)
                last_window_ts = start_ts  # only update after success
                logger.info("New window — start price: %.2f", window_start_price)

            if window_start_price is not None:
                live_price = fetch_live_price()
                set_kraken_data(KrakenData(
                    live_price=live_price,
                    window_start_price=window_start_price,
                    history=history,
                ))
                logger.debug("BTC live price: %.2f", live_price)

        except Exception as e:
            logger.error("Kraken fetcher error: %s", e)

        sleep(1)
