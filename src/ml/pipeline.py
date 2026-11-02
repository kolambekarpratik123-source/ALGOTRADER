"""End-to-end ranker run on synthetic data, with a built-in luck check.

The same run is repeated on several random markets (seeds), once WITH the hidden pattern and
once WITHOUT it (pure noise). The ranker only counts as working if:
  1. on pattern data, it beats buy-and-hold on most seeds and its IC is clearly positive, and
  2. on noise data, its IC stays near zero (it doesn't invent patterns).
One lucky seed proves nothing; this is why we look at all of them.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from src.backtest.costs import CostModel
from src.ml.features import build_features, build_target
from src.ml.model import WalkForwardConfig, evaluate_predictions, fit_final_model, rank_latest, walk_forward
from src.ml.portfolio import simulate_top_k
from src.ml.synthetic_market import generate_market

OUTPUT_FILE = Path(__file__).resolve().parents[2] / "data" / "ranker_results.json"


@dataclass
class RankerConfig:
    n_stocks: int = 100
    years: int = 6
    signal_strength: float = 1.0
    seeds: tuple[int, ...] = (1, 2, 3, 4, 5)
    horizon: int = 20          # predict ~1 month ahead
    rebalance_days: int = 20   # trade about once a month: keeps costs down
    top_k: int = 10
    hold_buffer: float = 2.0   # keep a stock while it's still in the top 20
    capital: float = 100_000.0
    max_monthly_loss_pct: float | None = 5.0


def run_once(cfg: RankerConfig, seed: int, signal_strength: float) -> dict:
    market = generate_market(cfg.n_stocks, cfg.years, signal_strength, seed=seed)
    feats = build_features(market)
    target = build_target(market, cfg.horizon)
    preds = walk_forward(feats, target, WalkForwardConfig(horizon=cfg.horizon), seed=seed)
    quality = evaluate_predictions(preds, cfg.horizon)
    port = simulate_top_k(
        preds, market,
        top_k=cfg.top_k,
        rebalance_days=cfg.rebalance_days,
        capital=cfg.capital,
        costs=CostModel(),
        max_monthly_loss_pct=cfg.max_monthly_loss_pct,
        hold_buffer=cfg.hold_buffer,
    )
    return {
        "seed": seed,
        "signal_strength": signal_strength,
        **quality,
        **{k: v for k, v in port.to_dict().items() if k != "equity_curve"},
        "beat_benchmark": bool(port.total_return_pct > port.benchmark_return_pct),
        "_equity_curve": port.to_dict()["equity_curve"],
        "_portfolio": port,
        "_preds": preds,
        "_cfg": cfg,
        "_market": market,
        "_features": feats,
        "_target": target,
    }


def _summarise(runs: list[dict]) -> dict:
    return {
        "seeds": len(runs),
        "avg_ic": round(float(np.mean([r["ic"] for r in runs])), 4),
        "avg_return_pct": round(float(np.mean([r["total_return_pct"] for r in runs])), 1),
        "avg_benchmark_pct": round(float(np.mean([r["benchmark_return_pct"] for r in runs])), 1),
        "beat_benchmark": int(sum(r["beat_benchmark"] for r in runs)),
        "worst_drawdown_pct": round(max(r["max_drawdown_pct"] for r in runs), 1),
        "worst_month_pct": round(min(r["worst_month_pct"] for r in runs), 1),
        "avg_costs": round(float(np.mean([r["total_costs"] for r in runs])), 0),
    }


def run_ranker(
    cfg: RankerConfig,
    on_progress=None,
    collect: list | None = None,
    output_file: Path | None = OUTPUT_FILE,
) -> dict:
    """Run all seeds. If `collect` is a list, the full detail of every run is appended to it.
    The report is saved to `output_file`; pass None (as tests do) to save nothing."""
    pattern_runs, noise_runs = [], []
    for seed in cfg.seeds:
        r = run_once(cfg, seed, cfg.signal_strength)
        pattern_runs.append(r)
        if on_progress:
            on_progress("pattern", r)
        n = run_once(cfg, seed, 0.0)
        noise_runs.append(n)
        if on_progress:
            on_progress("noise", n)

    if collect is not None:
        collect.extend(pattern_runs + noise_runs)
    pattern, noise = _summarise(pattern_runs), _summarise(noise_runs)
    found_pattern = pattern["avg_ic"] > 0.02 and pattern["beat_benchmark"] > len(cfg.seeds) / 2
    no_false_pattern = abs(noise["avg_ic"]) < 0.015
    verdict = (
        "PASS: finds the pattern when it exists and stays near zero skill on noise."
        if found_pattern and no_false_pattern
        else "FAIL: " + ("did not find the pattern reliably. " if not found_pattern else "")
        + ("found 'skill' in pure noise (overfitting). " if not no_false_pattern else "")
    )

    # Today's picks from the first pattern market, using a model trained on all its history
    first = pattern_runs[0]
    model = fit_final_model(first["_features"], first["_target"], seed=first["seed"])
    picks = rank_latest(model, first["_features"], cfg.top_k)

    def clean(r: dict) -> dict:
        return {k: v for k, v in r.items() if not k.startswith("_")}

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "data": "synthetic",
        "warning": "Synthetic markets only. This checks the method, not real-world profitability.",
        "config": {k: (list(v) if isinstance(v, tuple) else v) for k, v in asdict(cfg).items()},
        "verdict": verdict,
        "pattern_summary": pattern,
        "noise_summary": noise,
        "pattern_runs": [clean(r) for r in pattern_runs],
        "noise_runs": [clean(r) for r in noise_runs],
        "example_equity_curve": first["_equity_curve"],
        "latest_picks": [
            {"symbol": s, "score": round(float(row.score), 4), "date": str(row.date.date())}
            for s, row in picks.iterrows()
        ],
    }
    if output_file is not None:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(json.dumps(report, indent=2, default=str))
    return report
