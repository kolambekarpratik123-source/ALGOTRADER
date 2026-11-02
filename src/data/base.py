"""Abstract base class for market data providers."""

from abc import ABC, abstractmethod
from typing import Optional

from src.models import Candle, Quote


class MarketDataProvider(ABC):
    @abstractmethod
    async def connect(self) -> None:
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        pass

    @abstractmethod
    async def get_quote(self, symbol: str, exchange: str) -> Optional[Quote]:
        pass

    @abstractmethod
    async def get_candles(
        self,
        symbol: str,
        exchange: str,
        interval: str = "5minute",
        count: int = 100,
    ) -> list[Candle]:
        pass

    @abstractmethod
    async def subscribe(self, symbols: list[str], exchange: str) -> None:
        pass
