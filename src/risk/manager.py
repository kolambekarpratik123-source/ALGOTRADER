"""Risk management — capital protection rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from src.config import Settings
from src.models import Position, Quote, Side, Signal


@dataclass
class RiskDecision:
    allowed: bool
    reason: str
    quantity: int = 0
    stop_loss: float = 0.0
    take_profit: float = 0.0


@dataclass
class RiskManager:
    """Enforces position sizing, stop-loss/take-profit, and daily drawdown limits."""

    settings: Settings
    cash: float = field(init=False)
    daily_start_value: float = field(init=False)
    daily_pnl: float = 0.0
    _last_reset: date = field(default_factory=date.today)

    def __post_init__(self) -> None:
        self.cash = self.settings.initial_capital
        self.daily_start_value = self.settings.initial_capital

    @property
    def portfolio_value(self) -> float:
        return self.cash

    def reset_daily_if_needed(self, current_value: float) -> None:
        today = date.today()
        if today != self._last_reset:
            self.daily_start_value = current_value
            self.daily_pnl = 0.0
            self._last_reset = today

    def daily_loss_limit_hit(self, current_value: float) -> bool:
        self.reset_daily_if_needed(current_value)
        loss_pct = ((current_value - self.daily_start_value) / self.daily_start_value) * 100
        self.daily_pnl = current_value - self.daily_start_value
        return loss_pct <= -self.settings.max_daily_loss_pct

    def evaluate_entry(
        self,
        signal: Signal,
        quote: Quote,
        open_positions: list[Position],
        portfolio_value: float,
    ) -> RiskDecision:
        if self.daily_loss_limit_hit(portfolio_value):
            return RiskDecision(
                allowed=False,
                reason=f"Daily loss limit ({self.settings.max_daily_loss_pct}%) reached — trading halted",
            )

        if len(open_positions) >= self.settings.max_open_positions:
            return RiskDecision(
                allowed=False,
                reason=f"Max open positions ({self.settings.max_open_positions}) reached",
            )

        if any(p.symbol == signal.symbol for p in open_positions):
            return RiskDecision(
                allowed=False,
                reason=f"Already holding {signal.symbol}",
            )

        if signal.strength < 0.6:
            return RiskDecision(
                allowed=False,
                reason=f"Signal strength too low ({signal.strength:.2f})",
            )

        max_allocation = portfolio_value * (self.settings.max_position_size_pct / 100)
        quantity = int(max_allocation / quote.ltp)
        if quantity < 1:
            return RiskDecision(allowed=False, reason="Insufficient capital for 1 share")

        sl_pct = self.settings.default_stop_loss_pct / 100
        tp_pct = self.settings.default_take_profit_pct / 100

        if signal.side == Side.BUY:
            stop_loss = signal.stop_loss or round(quote.ltp * (1 - sl_pct), 2)
            take_profit = signal.take_profit or round(quote.ltp * (1 + tp_pct), 2)
        else:
            stop_loss = signal.stop_loss or round(quote.ltp * (1 + sl_pct), 2)
            take_profit = signal.take_profit or round(quote.ltp * (1 - tp_pct), 2)

        cost = quantity * quote.ltp
        if cost > self.cash and signal.side == Side.BUY:
            quantity = int(self.cash / quote.ltp)
            if quantity < 1:
                return RiskDecision(allowed=False, reason="Not enough cash")

        return RiskDecision(
            allowed=True,
            reason="Risk checks passed",
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

    def check_exit(self, position: Position, quote: Quote) -> tuple[bool, str]:

        ltp = quote.ltp

        if position.is_long:
            if ltp <= position.stop_loss:
                return True, f"Stop-loss hit at {ltp} (SL={position.stop_loss})"
            if ltp >= position.take_profit:
                return True, f"Take-profit hit at {ltp} (TP={position.take_profit})"
        else:
            if ltp >= position.stop_loss:
                return True, f"Stop-loss hit at {ltp} (SL={position.stop_loss})"
            if ltp <= position.take_profit:
                return True, f"Take-profit hit at {ltp} (TP={position.take_profit})"

        return False, ""
