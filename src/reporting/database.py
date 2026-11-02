"""Load ranker and backtest results into the SQLite reporting database."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "algotrader.db"
SCHEMA_FILE = ROOT / "sql" / "schema.sql"
ANALYSIS_DIR = ROOT / "sql" / "analysis"
BASELINE_FILE = ROOT / "data" / "baseline_results.json"

SECTORS = [
    "Banking", "IT Services", "Energy", "FMCG", "Pharma",
    "Auto", "Metals", "Infrastructure", "Telecom", "Financial Services",
]


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_FILE.read_text())


def _iso(d) -> str:
    return pd.Timestamp(d).strftime("%Y-%m-%d")


def load_dates(conn: sqlite3.Connection, dates: pd.DatetimeIndex) -> None:
    rows = [
        (_iso(d), d.year, (d.month - 1) // 3 + 1, d.month, d.strftime("%b"),
         d.strftime("%Y-%m"), int(d.isocalendar().week), d.strftime("%A"))
        for d in pd.DatetimeIndex(dates).unique().sort_values()
    ]
    conn.executemany("INSERT OR IGNORE INTO dim_date VALUES (?,?,?,?,?,?,?,?)", rows)


def load_synthetic_stocks(conn: sqlite3.Connection, symbols: list[str]) -> None:
    rng = np.random.default_rng(0)
    sectors = rng.choice(SECTORS, size=len(symbols))
    rows = [(s, f"Synthetic Co {s[3:]}", str(sec), "synthetic") for s, sec in zip(symbols, sectors)]
    conn.executemany("INSERT OR IGNORE INTO dim_stock VALUES (?,?,?,?)", rows)


def load_run(conn: sqlite3.Connection, run: dict, run_id: int, showcase: bool, data_source: str) -> None:
    """Insert one ranker run (from src.ml.pipeline) into the database."""
    cfg, port, preds, market = run["_cfg"], run["_portfolio"], run["_preds"], run["_market"]
    market_type = "real" if data_source != "synthetic" else ("noise" if run["signal_strength"] == 0 else "pattern")

    conn.execute(
        "INSERT INTO dim_run VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            run_id, datetime.now().isoformat(timespec="seconds"), data_source, market_type,
            run["seed"], run["signal_strength"], int(showcase), cfg.top_k, cfg.rebalance_days,
            cfg.horizon, cfg.capital, run["ic"], run["ic_tstat"], port.total_return_pct,
            port.benchmark_return_pct, port.cagr_pct, port.max_drawdown_pct, port.sharpe,
            port.worst_month_pct, port.total_costs, port.trades,
        ),
    )

    conn.executemany(
        "INSERT INTO fact_portfolio_daily VALUES (?,?,?,?)",
        [(run_id, _iso(d), round(float(e), 2), round(float(b), 2))
         for d, e, b in zip(port.equity.index, port.equity.values, port.benchmark.values)],
    )
    conn.executemany(
        "INSERT INTO fact_trade (run_id, date, symbol, side, quantity, price, value, charges, pnl, reason) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        [(run_id, _iso(t["date"]), t["symbol"], t["side"], int(t["quantity"]), t["price"],
          t["value"], t["charges"], t["pnl"], t["reason"]) for t in port.trade_log],
    )

    if showcase:
        px = pd.concat({k: market[k].stack() for k in ["open", "high", "low", "close", "volume"]}, axis=1)
        conn.executemany(
            "INSERT INTO fact_price VALUES (?,?,?,?,?,?,?,?)",
            [(run_id, _iso(d), s, r.open, r.high, r.low, r.close, int(r.volume))
             for (d, s), r in zip(px.index, px.itertuples(index=False))],
        )
        p = preds.copy()
        p["rank_in_day"] = p.groupby(level="date")["pred"].rank(ascending=False, method="first").astype(int)
        conn.executemany(
            "INSERT INTO fact_prediction VALUES (?,?,?,?,?,?,?)",
            [(run_id, _iso(d), s, round(float(r.pred), 6), int(r.rank_in_day),
              None if pd.isna(r.fwd_ret) else round(float(r.fwd_ret), 6), int(r.fold))
             for (d, s), r in zip(p.index, p.itertuples(index=False))],
        )


def load_baseline(conn: sqlite3.Connection, path: Path = BASELINE_FILE) -> int:
    """Load rule-strategy results from `main.py baseline`, if that file exists."""
    if not path.exists():
        return 0
    rep = json.loads(path.read_text())
    rows = [
        (rep.get("source", "synthetic").replace("yfinance", rep.get("exchange", "NSE").lower()),
         r["strategy"], r["symbol"], r.get("period_start"), r.get("period_end"),
         r["total_return_pct"], r.get("buy_hold_return_pct"), r["total_trades"], r["win_rate"],
         r["max_drawdown_pct"], r["sharpe_ratio"], r.get("total_costs"))
        for r in rep.get("results", [])
    ]
    conn.executemany("INSERT OR REPLACE INTO fact_strategy_backtest VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def build_database(runs: list[dict], db_path: Path = DB_PATH, data_source: str = "synthetic") -> Path:
    """Recreate the database from scratch with the given ranker runs.

    The first run is the showcase: its full prices and predictions are stored.
    """
    if db_path.exists():
        db_path.unlink()
    conn = connect(db_path)
    try:
        create_schema(conn)
        all_dates = pd.DatetimeIndex([])
        for run in runs:
            all_dates = all_dates.union(run["_market"]["close"].index)
        load_dates(conn, all_dates)
        load_synthetic_stocks(conn, list(runs[0]["_market"]["close"].columns))
        for i, run in enumerate(runs, start=1):
            load_run(conn, run, run_id=i, showcase=(i == 1), data_source=data_source)
        load_baseline(conn)
        conn.commit()
    finally:
        conn.close()
    return db_path


def run_analysis_queries(db_path: Path = DB_PATH) -> dict[str, pd.DataFrame]:
    """Run every query in sql/analysis/ and return the results by file name."""
    conn = connect(db_path)
    try:
        return {
            f.stem: pd.read_sql_query(f.read_text(), conn)
            for f in sorted(ANALYSIS_DIR.glob("*.sql"))
        }
    finally:
        conn.close()


def export_csv(db_path: Path = DB_PATH, out_dir: Path = ROOT / "data" / "exports") -> list[Path]:
    """Export every table to CSV, for Power BI (Get Data > Folder) or anything else."""
    out_dir.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        paths = []
        for t in tables:
            p = out_dir / f"{t}.csv"
            pd.read_sql_query(f"SELECT * FROM {t}", conn).to_csv(p, index=False)
            paths.append(p)
        return paths
    finally:
        conn.close()
