"""Moving Average Crossover Strategy (fast=9, slow=21) + RSI filter."""

import pandas as pd
from src.models import Candle, Side, Signal
from src.strategies.base import Strategy


class MovingAverageCrossover(Strategy):
    name: str = "ma_crossover"

    def __init__(self, fast_period: int = 9, slow_period: int = 21) -> None:
        self.fast_period = fast_period
        self.slow_period = slow_period

    def analyze(self, symbol: str, candles: list[Candle]) -> Signal | None:
        if len(candles) < self.slow_period + 2:
            return None

        df = pd.DataFrame([{"close": c.close} for c in candles])
        df["fast_ma"] = df["close"].rolling(window=self.fast_period).mean()
        df["slow_ma"] = df["close"].rolling(window=self.slow_period).mean()

        # Compute RSI 14
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df["rsi"] = 100 - (100 / (1 + rs))

        fast = df["fast_ma"].iloc[-1]
        slow = df["slow_ma"].iloc[-1]
        prev_fast = df["fast_ma"].iloc[-2]
        prev_slow = df["slow_ma"].iloc[-2]
        rsi = df["rsi"].iloc[-1] if not pd.isna(df["rsi"].iloc[-1]) else 50.0

        # Bullish crossover: fast crosses above slow & RSI not overbought (< 65)
        if prev_fast <= prev_slow and fast > slow and rsi < 65:
            strength = round(min(1.0, max(0.6, (65 - rsi) / 65 + 0.5)), 2)
            return Signal(
                symbol=symbol,
                side=Side.BUY,
                strength=strength,
                reason=f"MA {self.fast_period} crossed above MA {self.slow_period} (RSI: {rsi:.1f})",
            )

        return None
