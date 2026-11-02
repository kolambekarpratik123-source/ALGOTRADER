"""A synthetic stock market for building and testing the ranker.

Every stock follows: daily return = beta * market move + hidden drift + noise.

The hidden drift is a slow-moving trend per stock (it lasts weeks). Its size is set by
`signal_strength`:
- 0.0: no hidden drift. Prices are pure noise and NO model should be able to predict them.
       If the ranker "finds" something here, it is fooling itself.
- 1.0: a weak, realistic-sized pattern. A good model should find a small edge.
- 3.0: an obvious pattern, useful for checking the pipeline works at all.

Real markets are not built like this, so a result here only shows the code is correct.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DRIFT_PERSISTENCE = 0.98   # day-to-day correlation of the hidden drift (half-life ~35 days)
DRIFT_SCALE = 0.001        # daily drift std at signal_strength=1 (0.1% a day)


def generate_market(
    n_stocks: int = 100,
    years: int = 6,
    signal_strength: float = 1.0,
    seed: int = 42,
) -> dict[str, pd.DataFrame]:
    """Return wide DataFrames (rows = dates, columns = symbols): open, high, low, close, volume."""
    rng = np.random.default_rng(seed)
    days = years * 252
    dates = pd.bdate_range("2019-01-01", periods=days)
    symbols = [f"SYN{i:03d}" for i in range(n_stocks)]

    market = rng.normal(0.0004, 0.010, days)                 # whole-market daily move
    beta = rng.uniform(0.7, 1.3, n_stocks)
    idio_vol = rng.uniform(0.012, 0.025, n_stocks)

    # Hidden drift: AR(1) with unit long-run variance
    drift = np.zeros((days, n_stocks))
    shock_sd = np.sqrt(1 - DRIFT_PERSISTENCE**2)
    drift[0] = rng.normal(0, 1, n_stocks)
    for t in range(1, days):
        drift[t] = DRIFT_PERSISTENCE * drift[t - 1] + rng.normal(0, shock_sd, n_stocks)

    rets = (
        market[:, None] * beta[None, :]
        + signal_strength * DRIFT_SCALE * drift
        + rng.normal(0, 1, (days, n_stocks)) * idio_vol[None, :]
    )

    start = rng.uniform(50, 3000, n_stocks)
    close = start[None, :] * np.exp(np.cumsum(rets, axis=0))
    prev_close = np.vstack([start[None, :], close[:-1]])
    open_ = prev_close * (1 + rng.normal(0, 0.004, (days, n_stocks)))
    span = np.abs(rng.normal(0, 0.008, (days, n_stocks)))
    high = np.maximum(open_, close) * (1 + span)
    low = np.minimum(open_, close) * (1 - span)
    base_vol = rng.uniform(2e5, 5e6, n_stocks)
    volume = base_vol[None, :] * np.exp(rng.normal(0, 0.4, (days, n_stocks)) + 3 * np.abs(rets))

    frame = lambda a: pd.DataFrame(a, index=dates, columns=symbols)  # noqa: E731
    return {
        "open": frame(open_.round(2)),
        "high": frame(high.round(2)),
        "low": frame(low.round(2)),
        "close": frame(close.round(2)),
        "volume": frame(volume.round(0)),
    }
