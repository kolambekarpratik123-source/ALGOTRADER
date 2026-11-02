"""Backtest tests on synthetic data. These check the mechanics, not whether strategies make money."""

from datetime import datetime, timedelta

import pytest

from src.backtest import ZERO_COSTS, BacktestEngine, CostModel
from src.config import Settings
from src.data.historical import synthetic_daily_candles
from src.models import Candle, Side, Signal
from src.strategies.base import Strategy
from src.strategies.registry import get_strategy, list_strategies


class BuyOnce(Strategy):
    """Buys on the first candle it sees, then never again."""

    name = "buy_once"

    def __init__(self):
        self.fired = False

    def analyze(self, symbol, candles):
        if self.fired:
            return None
        self.fired = True
        return Signal(symbol=symbol, side=Side.BUY, strength=1.0, reason="test")


def flat_candles(n, price=100.0, start=datetime(2024, 1, 1)):
    return [
        Candle("T", "NSE", price, price, price, price, 1000, start + timedelta(days=i))
        for i in range(n)
    ]


def settings(**kw):
    base = dict(initial_capital=100_000, max_position_size_pct=100.0, max_daily_loss_pct=100.0)
    base.update(kw)
    return Settings(**base)


def test_costs_match_zerodha_delivery_roughly():
    c = CostModel(slippage_pct=0)
    # Rs 1 lakh round trip: ~0.1% STT each side + stamp + small fees + DP ≈ Rs 236
    total = c.charges(100_000, True) + c.charges(100_000, False)
    assert 220 < total < 250


def test_flat_market_loses_exactly_the_costs():
    candles = flat_candles(60)
    res = BacktestEngine(settings(), BuyOnce()).run("T", candles)
    assert res.total_trades == 1
    assert res.total_return_pct < 0
    assert res.total_costs > 0
    zero = BacktestEngine(settings(), BuyOnce(), ZERO_COSTS).run("T", candles)
    assert zero.total_return_pct == pytest.approx(0.0, abs=1e-9)


def test_entry_fills_at_next_open_not_signal_close():
    candles = flat_candles(40)
    # signal on candle 30 (close 100); candle 31 opens at 110
    c31 = candles[31]
    candles[31] = Candle("T", "NSE", 110, 110, 110, 110, 1000, c31.timestamp)
    res = BacktestEngine(settings(), BuyOnce(), ZERO_COSTS).run("T", candles)
    assert res.trades[0]["action"] == "BUY"
    assert res.trades[0]["price"] == pytest.approx(110)


def test_gap_down_fills_at_open_not_stop():
    candles = flat_candles(40)
    # bought at 100 on candle 31; stop is 1.5% below = 98.5. Candle 33 gaps to 90.
    t = candles[33].timestamp
    candles[33] = Candle("T", "NSE", 90, 91, 89, 90, 1000, t)
    res = BacktestEngine(settings(), BuyOnce(), ZERO_COSTS).run("T", candles)
    sell = [x for x in res.trades if x["action"] == "SELL"][0]
    assert sell["price"] == pytest.approx(90)
    assert "Stop-loss" in sell["reason"]


@pytest.mark.parametrize("name", list_strategies())
def test_every_strategy_runs_on_synthetic_data(name):
    candles = synthetic_daily_candles("TEST", years=2, seed=1)
    res = BacktestEngine(settings(), get_strategy(name)).run("TEST", candles)
    assert res.period_start and res.period_end
    assert res.max_drawdown_pct >= 0
    assert len(res.equity_curve) == len(candles) - 30
    for t in res.trades:
        assert t["qty"] > 0


def test_synthetic_data_is_reproducible():
    a = synthetic_daily_candles("X", years=1, seed=7)
    b = synthetic_daily_candles("X", years=1, seed=7)
    assert [c.close for c in a] == [c.close for c in b]
