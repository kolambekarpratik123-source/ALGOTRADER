"""MACD Indicator Crossover Strategy."""

import pandas as pd
from src.models import Candle, Side, Signal
from src.strategies.base import Strategy


class MACDStrategy(Strategy):
    name: str = "macd"

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9) -> None:
        self.fast = fast
        self.slow = slow
        self.signal = signal

    def analyze(self, symbol: str, candles: list[Candle]) -> Signal | None:
        if len(candles) < self.slow + self.signal + 5:
            return None

        df = pd.DataFrame([{"close": c.close} for c in candles])
        exp1 = df["close"].ewm(span=self.fast, adjust=False).mean()
        exp2 = df["close"].ewm(span=self.slow, adjust=False).mean()
        df["macd"] = exp1 - exp2
        df["signal"] = df["macd"].ewm(span=self.signal, adjust=False).mean()

        macd = df["macd"].iloc[-1]
        sig = df["signal"].iloc[-1]
        prev_macd = df["macd"].iloc[-2]
        prev_sig = df["signal"].iloc[-2]

        if prev_macd <= prev_sig and macd > sig and macd < 0:
            hist = macd - sig
            strength = round(min(1.0, max(0.65, 0.65 + abs(hist) / abs(sig or 1.0))), 2)
            return Signal(
                symbol=symbol,
                side=Side.BUY,
                strength=strength,
                reason=f"MACD line ({macd:.2f}) crossed above Signal line ({sig:.2f}) below zero",
            )

        return None
