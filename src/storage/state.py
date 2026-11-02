"""Persist engine state for dashboard and audit."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

STATE_DIR = Path(__file__).resolve().parent.parent.parent / "data"
STATE_FILE = STATE_DIR / "state.json"
TRADES_FILE = STATE_DIR / "trades.json"
BACKTEST_FILE = STATE_DIR / "backtest_results.json"


def ensure_data_dir() -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR


def save_state(state: dict) -> None:
    ensure_data_dir()
    state["updated_at"] = datetime.now().isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_trades(trades: list[dict]) -> None:
    ensure_data_dir()
    TRADES_FILE.write_text(json.dumps(trades, indent=2, default=str), encoding="utf-8")


def load_trades() -> list[dict]:
    if not TRADES_FILE.exists():
        return []
    return json.loads(TRADES_FILE.read_text(encoding="utf-8"))


def save_backtest_results(results: dict) -> None:
    ensure_data_dir()
    BACKTEST_FILE.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")


def load_backtest_results() -> dict:
    if not BACKTEST_FILE.exists():
        return {}
    return json.loads(BACKTEST_FILE.read_text(encoding="utf-8"))
