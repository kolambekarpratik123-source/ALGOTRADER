"""Turn prices into model inputs. Every feature uses only data up to that day's close."""

from __future__ import annotations

import numpy as np
import pandas as pd

FEATURES = [
    "ret_1", "ret_5", "ret_20", "ret_60",
    "vol_20", "rsi_14", "dist_ma50", "macd_hist", "volume_ratio",
]


def _rsi(close: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    return 100 - 100 / (1 + gain / loss.replace(0, np.nan))


def build_features(market: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Long DataFrame indexed by (date, symbol), one column per feature.

    Each feature is converted to its rank among all stocks that day (0 to 1), so the model
    learns "which stocks look best relative to the others", not absolute price levels.
    """
    close, volume = market["close"], market["volume"]
    daily_ret = close.pct_change()
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26

    raw = {
        "ret_1": daily_ret,
        "ret_5": close.pct_change(5),
        "ret_20": close.pct_change(20),
        "ret_60": close.pct_change(60),
        "vol_20": daily_ret.rolling(20).std(),
        "rsi_14": _rsi(close),
        "dist_ma50": close / close.rolling(50).mean() - 1,
        "macd_hist": (macd - macd.ewm(span=9, adjust=False).mean()) / close,
        "volume_ratio": volume / volume.rolling(20).mean(),
    }
    ranked = {name: df.rank(axis=1, pct=True) for name, df in raw.items()}
    out = pd.concat({k: v.stack(future_stack=True) for k, v in ranked.items()}, axis=1)
    out.index.names = ["date", "symbol"]
    return out[FEATURES]


def build_target(market: dict[str, pd.DataFrame], horizon: int = 5) -> pd.DataFrame:
    """What we try to predict: return from tomorrow's open to the open `horizon` days later.

    Buying at tomorrow's open (not today's close) matches how the trades actually happen.
    Returns columns: fwd_ret (raw) and fwd_rank (rank among stocks that day, 0 to 1).
    """
    opn = market["open"]
    fwd = opn.shift(-(horizon + 1)) / opn.shift(-1) - 1
    out = pd.concat(
        {"fwd_ret": fwd.stack(future_stack=True), "fwd_rank": fwd.rank(axis=1, pct=True).stack(future_stack=True)},
        axis=1,
    )
    out.index.names = ["date", "symbol"]
    return out
