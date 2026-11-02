"""RSI Overbought / Oversold Strategy."""

import pandas as pd
from src.models import Candle, Side, Signal
from src.strategies.base import Strategy


class RSIStrategy(Strategy):
    name: str = "rsi"

    def __init__(self, period: int = 14, oversold: float = 30.0, overbought: float = 70.0) -> None:
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    def analyze(self, symbol: str, candles: list[Candle]) -> Signal | None:
        if len(candles) < self.period + 5:
            return None

        df = pd.DataFrame([{"close": c.close} for c in candles])
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.period).mean()
        rs = gain / loss
        rsi = (100 - (100 / (1 + rs))).iloc[-1]

        if pd.isna(rsi):
            return None

        if rsi < self.oversold:
            strength = round(min(1.0, max(0.6, (self.oversold - rsi) / self.oversold + 0.6)), 2)
            return Signal(
                symbol=symbol,
                side=Side.BUY,
                strength=strength,
                reason=f"RSI oversold at {rsi:.1f} (< {self.oversold})",
            )

        return None
