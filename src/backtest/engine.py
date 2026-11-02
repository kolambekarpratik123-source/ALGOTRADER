"""Backtest engine: simulate a strategy on historical candles, with realistic fills and costs.

How fills work (to avoid results that look better than reality):
- A signal on a candle's close is filled at the NEXT candle's open, plus slippage.
- Stop-loss and take-profit are checked against each candle's low and high.
  If the price gaps past the stop, the fill is at the open, not at the stop.
  If both could have hit on the same candle, the stop-loss is assumed (worst case).
- Every buy and sell pays brokerage, taxes and charges from the CostModel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import numpy as np

from src.backtest.costs import CostModel
from src.config import Settings
from src.models import Candle, Position, Quote, Side
from src.risk.manager import RiskManager
from src.strategies.base import Strategy

WARMUP_CANDLES = 30
LOOKBACK_CANDLES = 250  # history passed to the strategy each step; enough for all current indicators


@dataclass
class BacktestResult:
    symbol: str
    strategy: str
    total_return_pct: float
    total_trades: int
    win_rate: float
    max_drawdown_pct: float
    sharpe_ratio: float
    total_costs: float = 0.0
    buy_hold_return_pct: float = 0.0
    exposure_pct: float = 0.0
    period_start: str = ""
    period_end: str = ""
    equity_curve: list[dict] = field(default_factory=list)
    trades: list[dict] = field(default_factory=list)

    @property
    def beats_buy_hold(self) -> bool:
        return self.total_return_pct > self.buy_hold_return_pct

    def to_dict(self, include_curves: bool = True) -> dict:
        d = {
            "symbol": self.symbol,
            "strategy": self.strategy,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "total_return_pct": round(self.total_return_pct, 2),
            "buy_hold_return_pct": round(self.buy_hold_return_pct, 2),
            "total_trades": self.total_trades,
            "win_rate": round(self.win_rate, 1),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 2),
            "total_costs": round(self.total_costs, 2),
            "exposure_pct": round(self.exposure_pct, 1),
        }
        if include_curves:
            d["equity_curve"] = self.equity_curve
            d["trades"] = self.trades
        return d


def _ts(c: Candle) -> str:
    return c.timestamp.isoformat() if isinstance(c.timestamp, datetime) else str(c.timestamp)


def _quote(symbol: str, exchange: str, c: Candle) -> Quote:
    return Quote(
        symbol=symbol,
        exchange=exchange,
        ltp=c.close,
        open=c.open,
        high=c.high,
        low=c.low,
        close=c.close,
        volume=c.volume,
        timestamp=c.timestamp,
    )


def _candle_date(c: Candle) -> date | None:
    return c.timestamp.date() if isinstance(c.timestamp, datetime) else None


@dataclass
class _PendingEntry:
    reason: str
    quantity: int
    sl_pct: float  # stop distance as a fraction of price
    tp_pct: float  # target distance as a fraction of price


class BacktestEngine:
    def __init__(
        self,
        settings: Settings,
        strategy: Strategy,
        costs: CostModel | None = None,
    ) -> None:
        self.settings = settings
        self.strategy = strategy
        self.costs = costs or CostModel()
        self.risk = RiskManager(settings)

    def run(self, symbol: str, candles: list[Candle]) -> BacktestResult:
        exchange = self.settings.exchange.value
        capital = self.settings.initial_capital

        if len(candles) <= WARMUP_CANDLES + 1:
            return BacktestResult(
                symbol=symbol,
                strategy=self.strategy.name,
                total_return_pct=0.0,
                total_trades=0,
                win_rate=0.0,
                max_drawdown_pct=0.0,
                sharpe_ratio=0.0,
            )

        cash = capital
        position: Position | None = None
        entry_cost = 0.0  # rupees paid to open the current position, incl. charges
        pending: _PendingEntry | None = None
        trades: list[dict] = []
        equity_curve: list[dict] = []
        total_costs = 0.0
        candles_in_market = 0
        peak = capital
        max_dd = 0.0
        last_day: date | None = None

        def close_position(c: Candle, raw_price: float, reason: str) -> None:
            nonlocal cash, position, total_costs, entry_cost
            assert position is not None
            px = self.costs.fill_price(raw_price, is_buy=False)
            turnover = px * position.quantity
            fee = self.costs.charges(turnover, is_buy=False)
            cash += turnover - fee
            total_costs += fee
            trades.append(
                {
                    "time": _ts(c),
                    "action": "SELL",
                    "price": round(px, 2),
                    "qty": position.quantity,
                    "charges": round(fee, 2),
                    "pnl": round(turnover - fee - entry_cost, 2),
                    "reason": reason,
                }
            )
            position = None
            entry_cost = 0.0

        for i in range(WARMUP_CANDLES, len(candles)):
            c = candles[i]

            # New trading day: reset the daily loss baseline to current equity
            day = _candle_date(c)
            if day is not None and day != last_day:
                pos_val = position.quantity * candles[i - 1].close if position else 0.0
                self.risk.daily_start_value = cash + pos_val
                self.risk._last_reset = date.today()  # stop the manager resetting on wall-clock date
                last_day = day

            # 1. Fill yesterday's signal at today's open
            if pending is not None and position is None:
                px = self.costs.fill_price(c.open, is_buy=True)
                qty = pending.quantity
                fee = self.costs.charges(px * qty, is_buy=True)
                while qty > 0 and px * qty + fee > cash:
                    qty -= 1
                    fee = self.costs.charges(px * qty, is_buy=True)
                if qty > 0:
                    cash -= px * qty + fee
                    total_costs += fee
                    entry_cost = px * qty + fee
                    position = Position(
                        symbol=symbol,
                        exchange=exchange,
                        quantity=qty,
                        avg_price=px,
                        stop_loss=round(px * (1 - pending.sl_pct), 2),
                        take_profit=round(px * (1 + pending.tp_pct), 2),
                    )
                    trades.append(
                        {
                            "time": _ts(c),
                            "action": "BUY",
                            "price": round(px, 2),
                            "qty": qty,
                            "charges": round(fee, 2),
                            "pnl": 0.0,
                            "reason": pending.reason,
                        }
                    )
                pending = None

            # 2. Stop-loss / take-profit inside today's range (stop checked first: worst case)
            if position is not None:
                sl, tp = position.stop_loss, position.take_profit
                if c.low <= sl:
                    close_position(c, min(c.open, sl), f"Stop-loss hit (SL={sl})")
                elif c.high >= tp:
                    close_position(c, max(c.open, tp), f"Take-profit hit (TP={tp})")

            # 3. Look for a new entry on today's close, to fill at tomorrow's open
            if position is None and i < len(candles) - 1:
                signal = self.strategy.analyze(symbol, candles[max(0, i + 1 - LOOKBACK_CANDLES) : i + 1])
                if signal and signal.side == Side.BUY:
                    decision = self.risk.evaluate_entry(
                        signal, _quote(symbol, exchange, c), [], cash
                    )
                    if decision.allowed:
                        pending = _PendingEntry(
                            reason=signal.reason,
                            quantity=decision.quantity,
                            sl_pct=1 - decision.stop_loss / c.close,
                            tp_pct=decision.take_profit / c.close - 1,
                        )

            # Record equity
            pos_val = position.quantity * c.close if position else 0.0
            equity = cash + pos_val
            if position is not None:
                candles_in_market += 1
            equity_curve.append({"time": _ts(c), "equity": round(equity, 2)})
            peak = max(peak, equity)
            max_dd = max(max_dd, (peak - equity) / peak * 100)

        # Close anything still open at the last close
        if position is not None:
            close_position(candles[-1], candles[-1].close, "End of backtest")
            equity_curve[-1]["equity"] = round(cash, 2)

        total_return_pct = (cash - capital) / capital * 100

        sells = [t for t in trades if t["action"] == "SELL"]
        wins = [t for t in sells if t["pnl"] > 0]
        win_rate = len(wins) / len(sells) * 100 if sells else 0.0

        eq = np.array([p["equity"] for p in equity_curve], dtype=float)
        rets = np.diff(eq) / eq[:-1] if len(eq) > 1 else np.array([])
        sharpe = (
            float(rets.mean() / rets.std() * np.sqrt(252))
            if len(rets) > 1 and rets.std() > 0
            else 0.0
        )

        return BacktestResult(
            symbol=symbol,
            strategy=self.strategy.name,
            total_return_pct=total_return_pct,
            total_trades=len(sells),
            win_rate=win_rate,
            max_drawdown_pct=max_dd,
            sharpe_ratio=sharpe,
            total_costs=total_costs,
            buy_hold_return_pct=self.buy_and_hold_return(candles),
            exposure_pct=candles_in_market / max(1, len(candles) - WARMUP_CANDLES) * 100,
            period_start=_ts(candles[WARMUP_CANDLES]),
            period_end=_ts(candles[-1]),
            equity_curve=equity_curve,
            trades=trades,
        )

    def buy_and_hold_return(self, candles: list[Candle]) -> float:
        """Return % from buying at the first tested open and selling at the last close, after costs."""
        if len(candles) <= WARMUP_CANDLES:
            return 0.0
        capital = self.settings.initial_capital
        buy_px = self.costs.fill_price(candles[WARMUP_CANDLES].open, is_buy=True)
        qty = int(capital / buy_px)
        while qty > 0 and buy_px * qty + self.costs.charges(buy_px * qty, True) > capital:
            qty -= 1
        if qty == 0:
            return 0.0
        spent = buy_px * qty + self.costs.charges(buy_px * qty, True)
        sell_px = self.costs.fill_price(candles[-1].close, is_buy=False)
        got = sell_px * qty - self.costs.charges(sell_px * qty, False)
        return (got - spent) / capital * 100
