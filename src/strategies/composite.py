"""Composite Multi-Strategy Ensemble."""

from src.models import Candle, Side, Signal
from src.strategies.base import Strategy
from src.strategies.ma_crossover import MovingAverageCrossover
from src.strategies.macd import MACDStrategy
from src.strategies.rsi import RSIStrategy


class CompositeStrategy(Strategy):
    name: str = "composite"

    def __init__(
        self,
        strategies: list[Strategy] | None = None,
        min_agree: int = 2,
    ) -> None:
        self.strategies = strategies or [
            MovingAverageCrossover(),
            RSIStrategy(),
            MACDStrategy(),
        ]
        self.min_agree = min_agree

    def analyze(self, symbol: str, candles: list[Candle]) -> Signal | None:
        buy_signals: list[Signal] = []

        for strat in self.strategies:
            sig = strat.analyze(symbol, candles)
            if sig and sig.side == Side.BUY:
                buy_signals.append(sig)

        if len(buy_signals) >= self.min_agree:
            avg_strength = round(sum(s.strength for s in buy_signals) / len(buy_signals), 2)
            reasons = " | ".join(f"[{s.reason}]" for s in buy_signals)
            return Signal(
                symbol=symbol,
                side=Side.BUY,
                strength=avg_strength,
                reason=f"Ensemble consensus ({len(buy_signals)}/{len(self.strategies)} agreed): {reasons}",
            )

        return None
