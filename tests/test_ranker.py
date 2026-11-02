"""Ranker tests on synthetic markets. Small sizes so they run quickly."""

import numpy as np
import pytest

from src.ml.features import FEATURES, build_features, build_target
from src.ml.model import WalkForwardConfig, evaluate_predictions, walk_forward
from src.ml.portfolio import simulate_top_k
from src.ml.synthetic_market import generate_market

CFG = WalkForwardConfig(train_days=252, test_days=126, horizon=20)


def run(signal, seed):
    m = generate_market(n_stocks=50, years=4, signal_strength=signal, seed=seed)
    f, y = build_features(m), build_target(m, CFG.horizon)
    p = walk_forward(f, y, CFG, seed=seed)
    return m, p, evaluate_predictions(p, CFG.horizon)


def test_features_do_not_look_ahead():
    m = generate_market(n_stocks=20, years=2, signal_strength=1.0, seed=0)
    before = build_features(m)
    cut = m["close"].index[300]
    changed = {k: v.copy() for k, v in m.items()}
    for v in changed.values():
        v.loc[v.index > cut] *= 1.5  # rewrite the future
    after = build_features(changed)
    idx = before.index.get_level_values("date") <= cut
    np.testing.assert_allclose(
        before.loc[idx, FEATURES].to_numpy(), after.loc[idx, FEATURES].to_numpy(), equal_nan=True
    )


def test_walk_forward_never_trains_on_test_period():
    m, p, _ = run(1.0, 0)
    dates = m["close"].index
    first_test = p.index.get_level_values("date").min()
    # first test date must come after train_days + horizon gap
    assert dates.get_loc(first_test) >= CFG.train_days + CFG.horizon


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_no_skill_on_pure_noise(seed):
    _, _, ev = run(0.0, seed)
    assert abs(ev["ic"]) < 0.03


def test_finds_strong_pattern():
    _, _, ev = run(3.0, 1)
    assert ev["ic"] > 0.05
    assert ev["decile_spread_pct"] > 0


def test_portfolio_pays_costs_and_respects_top_k():
    m, p, _ = run(3.0, 1)
    r = simulate_top_k(p, m, top_k=5, rebalance_days=20)
    assert r.total_costs > 0
    assert r.trades > 0
    assert len(r.equity) == len(r.benchmark)


def test_monthly_loss_limit_reduces_trading():
    m, p, _ = run(0.0, 2)
    free = simulate_top_k(p, m, top_k=5, rebalance_days=5)
    capped = simulate_top_k(p, m, top_k=5, rebalance_days=5, max_monthly_loss_pct=1.0)
    assert capped.trades <= free.trades
