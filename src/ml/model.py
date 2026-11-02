"""Ranking model with walk-forward testing.

Walk-forward means: train on the past, predict the next few months, then move forward and
repeat. The model never sees the period it is being scored on. A gap of `horizon` days is
left between training and testing so the training targets can't peek into the test period.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from src.ml.features import FEATURES


def make_model(seed: int = 0) -> HistGradientBoostingRegressor:
    # Small, heavily regularised trees: stock data is mostly noise and big models memorise it.
    return HistGradientBoostingRegressor(
        max_iter=150,
        learning_rate=0.05,
        max_depth=3,
        min_samples_leaf=500,
        l2_regularization=1.0,
        random_state=seed,
    )


@dataclass
class WalkForwardConfig:
    train_days: int = 504     # ~2 years of history per training run
    test_days: int = 126      # ~6 months predicted before retraining
    horizon: int = 5          # days ahead we predict; also the gap between train and test
    expanding: bool = True    # keep all past data when retraining (vs. a fixed window)


def walk_forward(
    features: pd.DataFrame,
    target: pd.DataFrame,
    cfg: WalkForwardConfig | None = None,
    seed: int = 0,
) -> pd.DataFrame:
    """Out-of-sample predictions for every test period.

    Returns a DataFrame indexed by (date, symbol) with columns: pred, fwd_ret, fwd_rank, fold.
    """
    cfg = cfg or WalkForwardConfig()
    data = features.join(target, how="inner").dropna()
    dates = data.index.get_level_values("date").unique().sort_values()

    outputs = []
    fold = 0
    test_start = cfg.train_days + cfg.horizon
    while test_start < len(dates):
        train_end = test_start - cfg.horizon          # exclusive
        train_begin = 0 if cfg.expanding else max(0, train_end - cfg.train_days)
        test_end = min(test_start + cfg.test_days, len(dates))

        train_dates = dates[train_begin:train_end]
        test_dates = dates[test_start:test_end]
        tr = data.loc[data.index.get_level_values("date").isin(train_dates)]
        te = data.loc[data.index.get_level_values("date").isin(test_dates)]

        model = make_model(seed)
        model.fit(tr[FEATURES].to_numpy(), tr["fwd_rank"].to_numpy())
        out = te[["fwd_ret", "fwd_rank"]].copy()
        out["pred"] = model.predict(te[FEATURES].to_numpy())
        out["fold"] = fold
        outputs.append(out)

        fold += 1
        test_start = test_end

    if not outputs:
        raise ValueError("Not enough history for one walk-forward fold. Use more years of data.")
    return pd.concat(outputs)


def fit_final_model(features: pd.DataFrame, target: pd.DataFrame, seed: int = 0):
    """Train on all available history, for ranking stocks today."""
    data = features.join(target, how="inner").dropna()
    model = make_model(seed)
    model.fit(data[FEATURES].to_numpy(), data["fwd_rank"].to_numpy())
    return model


def rank_latest(model, features: pd.DataFrame, top: int = 10) -> pd.DataFrame:
    """Score every stock on the most recent date and return the top `top`."""
    last = features.index.get_level_values("date").max()
    today = features.xs(last, level="date").dropna()
    scores = pd.Series(model.predict(today[FEATURES].to_numpy()), index=today.index, name="score")
    return scores.sort_values(ascending=False).head(top).to_frame().assign(date=last)


def evaluate_predictions(preds: pd.DataFrame, horizon: int = 5) -> dict:
    """How good were the out-of-sample rankings?

    - ic: average daily rank correlation between prediction and actual forward return.
      0 = no skill. Around 0.02-0.05 is already useful in real markets.
    - ic_tstat: how sure we are the IC isn't luck (above ~2 is meaningful). Uses only every
      `horizon`-th day so overlapping forward returns don't inflate it.
    - decile_spread_pct: avg forward return of the top 10% minus the bottom 10%.
    """
    def daily_ic(g: pd.DataFrame) -> float:
        return g["pred"].rank().corr(g["fwd_ret"].rank())

    ic = preds.groupby(level="date").apply(daily_ic).dropna()
    ic_sparse = ic.iloc[::horizon]
    tstat = (
        float(ic_sparse.mean() / ic_sparse.std() * np.sqrt(len(ic_sparse)))
        if len(ic_sparse) > 1 and ic_sparse.std() > 0
        else 0.0
    )

    def spread(g: pd.DataFrame) -> float:
        q = g["pred"].rank(pct=True)
        return g.loc[q > 0.9, "fwd_ret"].mean() - g.loc[q <= 0.1, "fwd_ret"].mean()

    spreads = preds.groupby(level="date").apply(spread).dropna()
    return {
        "ic": round(float(ic.mean()), 4),
        "ic_tstat": round(tstat, 2),
        "ic_positive_days_pct": round(float((ic > 0).mean() * 100), 1),
        "decile_spread_pct": round(float(spreads.mean() * 100), 3),
        "test_days": int(len(ic)),
        "folds": int(preds["fold"].nunique()),
    }
