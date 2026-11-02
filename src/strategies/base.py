"""Trading strategy framework."""

from abc import ABC, abstractmethod

from src.models import Candle, Signal


class Strategy(ABC):
    name: str = "base"

    @abstractmethod
    def analyze(self, symbol: str, candles: list[Candle]) -> Signal | None:
        ...
