"""Run every strategy on every symbol and summarise against buy-and-hold.

This is the baseline any future model (including the AI ranker) has to beat.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.backtest.costs import CostModel
from src.backtest.engine import BacktestEngine, BacktestResult
from src.config import Settings
from src.data.historical import load_daily_candles
from src.strategies.registry import get_strategy, list_strategies

DEFAULT_SYMBOLS = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "HINDUNILVR", "ITC", "SBIN", "BHARTIARTL", "LT",
]
OUTPUT_FILE = Path(__file__).resolve().parents[2] / "data" / "baseline_results.json"


def run_baseline(
    settings: Settings,
    symbols: list[str],
    source: str = "yfinance",
    years: int = 5,
    strategies: list[str] | None = None,
    costs: CostModel | None = None,
    on_progress=None,
) -> dict:
    strategies = strategies or list_strategies()
    results: list[BacktestResult] = []
    errors: dict[str, str] = {}

    for sym in symbols:
        try:
            candles = load_daily_candles(sym, settings.exchange.value, years, source=source)
        except Exception as exc:  # network, bad symbol, etc.
            errors[sym] = str(exc)
            continue
        for name in strategies:
            res = BacktestEngine(settings, get_strategy(name), costs).run(sym, candles)
            results.append(res)
            if on_progress:
                on_progress(res)

    summary = []
    for name in strategies:
        rs = [r for r in results if r.strategy == name]
        if not rs:
            continue
        n = len(rs)
        summary.append(
            {
                "strategy": name,
                "symbols_tested": n,
                "avg_return_pct": round(sum(r.total_return_pct for r in rs) / n, 2),
                "avg_buy_hold_pct": round(sum(r.buy_hold_return_pct for r in rs) / n, 2),
                "beat_buy_hold": sum(r.beats_buy_hold for r in rs),
                "avg_sharpe": round(sum(r.sharpe_ratio for r in rs) / n, 2),
                "worst_drawdown_pct": round(max(r.max_drawdown_pct for r in rs), 2),
                "total_trades": sum(r.total_trades for r in rs),
                "avg_win_rate": round(sum(r.win_rate for r in rs) / n, 1),
                "total_costs": round(sum(r.total_costs for r in rs), 2),
            }
        )

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "exchange": settings.exchange.value,
        "years": years,
        "initial_capital": settings.initial_capital,
        "position_size_pct": settings.max_position_size_pct,
        "stop_loss_pct": settings.default_stop_loss_pct,
        "take_profit_pct": settings.default_take_profit_pct,
        "warning": (
            "Synthetic data: these numbers only show the code runs. They say nothing about real markets."
            if source == "synthetic"
            else ""
        ),
        "summary": summary,
        "results": [r.to_dict(include_curves=False) for r in results],
        "errors": errors,
    }
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(report, indent=2))
    return report
