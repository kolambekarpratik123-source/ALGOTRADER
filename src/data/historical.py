"""Daily historical candles for backtesting.

Two sources:
- "yfinance": real NSE/BSE daily prices from Yahoo Finance, cached to data/history/.
  Use this for every result you want to trust.
- "synthetic": random prices with a fixed seed. Use it only to check that code runs.
  It has no real patterns, so a strategy's result on it means nothing.
"""

from __future__ import annotations

import math
import random
import zlib
from datetime import datetime, timedelta
from pathlib import Path

from src.models import Candle

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "history"
YAHOO_SUFFIX = {"NSE": ".NS", "BSE": ".BO"}
SOURCES = ("yfinance", "synthetic")


def load_daily_candles(
    symbol: str,
    exchange: str = "NSE",
    years: int = 5,
    source: str = "yfinance",
    refresh: bool = False,
    seed: int | None = None,
) -> list[Candle]:
    """Return daily candles, oldest first."""
    if source == "yfinance":
        return _load_yfinance(symbol, exchange, years, refresh)
    if source == "synthetic":
        return synthetic_daily_candles(symbol, exchange, years, seed=seed)
    raise ValueError(f"Unknown source '{source}'. Use one of: {', '.join(SOURCES)}")


def _load_yfinance(symbol: str, exchange: str, years: int, refresh: bool) -> list[Candle]:
    import pandas as pd

    sym = symbol.upper()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{sym}_{exchange}_{years}y.csv"

    fresh = cache_file.exists() and (
        datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime) < timedelta(hours=12)
    )
    if fresh and not refresh:
        df = pd.read_csv(cache_file, parse_dates=["date"])
    else:
        try:
            import yfinance as yf
        except ImportError as exc:
            raise ImportError("Install yfinance: pip install yfinance") from exc

        ticker = sym + YAHOO_SUFFIX.get(exchange.upper(), ".NS")
        raw = yf.download(
            ticker,
            period=f"{years}y",
            interval="1d",
            auto_adjust=True,  # adjust for splits and dividends
            progress=False,
        )
        if raw is None or raw.empty:
            raise RuntimeError(
                f"No data for {ticker}. Check the symbol and your internet connection."
            )
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        df = raw.reset_index().rename(columns=str.lower)
        df = df[["date", "open", "high", "low", "close", "volume"]].dropna()
        df.to_csv(cache_file, index=False)

    return [
        Candle(
            symbol=sym,
            exchange=exchange,
            open=float(r.open),
            high=float(r.high),
            low=float(r.low),
            close=float(r.close),
            volume=int(r.volume),
            timestamp=pd.Timestamp(r.date).to_pydatetime(),
        )
        for r in df.itertuples(index=False)
    ]


def synthetic_daily_candles(
    symbol: str,
    exchange: str = "NSE",
    years: int = 5,
    start_price: float = 1000.0,
    annual_drift: float = 0.10,
    annual_vol: float = 0.25,
    seed: int | None = None,
) -> list[Candle]:
    """Random-walk daily prices (geometric Brownian motion). For code tests only."""
    rng = random.Random(seed if seed is not None else zlib.crc32(symbol.upper().encode()))
    days = years * 252
    dt = 1 / 252
    mu = (annual_drift - 0.5 * annual_vol**2) * dt
    sigma = annual_vol * math.sqrt(dt)

    candles: list[Candle] = []
    price = start_price
    day = datetime(2020, 1, 1)
    for _ in range(days):
        day += timedelta(days=1)
        while day.weekday() >= 5:
            day += timedelta(days=1)
        open_p = price * (1 + rng.gauss(0, sigma * 0.3))
        close_p = price * math.exp(mu + sigma * rng.gauss(0, 1))
        high_p = max(open_p, close_p) * (1 + abs(rng.gauss(0, sigma * 0.5)))
        low_p = min(open_p, close_p) * (1 - abs(rng.gauss(0, sigma * 0.5)))
        candles.append(
            Candle(
                symbol=symbol.upper(),
                exchange=exchange,
                open=round(open_p, 2),
                high=round(high_p, 2),
                low=round(low_p, 2),
                close=round(close_p, 2),
                volume=rng.randint(100_000, 5_000_000),
                timestamp=day,
            )
        )
        price = close_p
    return candles
