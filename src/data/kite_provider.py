"""Enhanced Kite data provider with WebSocket support."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from src.data.base import MarketDataProvider
from src.data.kite_websocket import KiteWebSocket
from src.models import Candle, Quote


class KiteDataProvider(MarketDataProvider):
    """
    Live BSE/NSE data via Zerodha Kite Connect.
    Uses REST for quotes/candles and WebSocket for live ticks.
    """

    INTERVAL_MAP = {
        "minute": "minute",
        "5minute": "5minute",
        "15minute": "15minute",
        "day": "day",
    }

    INTERVAL_DAYS = {
        "minute": 7,
        "5minute": 30,
        "15minute": 60,
        "day": 365,
    }

    def __init__(self, api_key: str, access_token: str):
        self._api_key = api_key
        self._access_token = access_token
        self._kite = None
        self._instruments: dict[str, int] = {}
        self._ws: KiteWebSocket | None = None
        self._subscribed: list[str] = []

    async def connect(self) -> None:
        try:
            from kiteconnect import KiteConnect
        except ImportError as exc:
            raise ImportError("Install kiteconnect: pip install kiteconnect") from exc

        self._kite = KiteConnect(api_key=self._api_key)
        self._kite.set_access_token(self._access_token)

        loop = asyncio.get_event_loop()
        instruments = await loop.run_in_executor(None, self._kite.instruments)
        for inst in instruments:
            key = f"{inst['exchange']}:{inst['tradingsymbol']}"
            self._instruments[key] = inst["instrument_token"]

        self._ws = KiteWebSocket(self._api_key, self._access_token)

    async def disconnect(self) -> None:
        if self._ws:
            await self._ws.disconnect()
        self._kite = None

    def _token(self, symbol: str, exchange: str) -> int:
        key = f"{exchange}:{symbol.upper()}"
        token = self._instruments.get(key)
        if token is None:
            raise ValueError(f"Unknown instrument: {key}. Check symbol and exchange.")
        return token

    async def get_quote(self, symbol: str, exchange: str) -> Optional[Quote]:
        symbol = symbol.upper()

        if self._ws:
            live = self._ws.get_latest(symbol)
            if live:
                return live

        if not self._kite:
            return None

        key = f"{exchange}:{symbol}"
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, self._kite.quote, [key])
        q = data.get(key, {})
        ohlc = q.get("ohlc", {})
        return Quote(
            symbol=symbol,
            exchange=exchange,
            ltp=float(q.get("last_price", 0)),
            open=float(ohlc.get("open", 0)),
            high=float(ohlc.get("high", 0)),
            low=float(ohlc.get("low", 0)),
            close=float(ohlc.get("close", 0)),
            volume=int(q.get("volume", 0)),
            timestamp=datetime.now(),
        )

    async def get_candles(
        self,
        symbol: str,
        exchange: str,
        interval: str = "5minute",
        count: int = 100,
    ) -> list[Candle]:
        if not self._kite:
            return []

        token = self._token(symbol, exchange)
        kite_interval = self.INTERVAL_MAP.get(interval, "5minute")
        days = self.INTERVAL_DAYS.get(interval, 30)
        to_date = datetime.now()
        from_date = to_date - timedelta(days=days)

        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(
            None,
            lambda: self._kite.historical_data(token, from_date, to_date, kite_interval),
        )
        raw = raw[-count:]

        return [
            Candle(
                symbol=symbol.upper(),
                exchange=exchange,
                open=float(c["open"]),
                high=float(c["high"]),
                low=float(c["low"]),
                close=float(c["close"]),
                volume=int(c["volume"]),
                timestamp=c["date"],
            )
            for c in raw
        ]

    async def subscribe(self, symbols: list[str], exchange: str) -> None:
        if not self._ws or not self._kite:
            return

        token_map: dict[int, tuple[str, str]] = {}
        tokens: list[int] = []
        for symbol in symbols:
            token = self._token(symbol, exchange)
            token_map[token] = (symbol.upper(), exchange)
            tokens.append(token)

        self._ws.register_instruments(token_map)
        await self._ws.connect(tokens)
        self._subscribed = [s.upper() for s in symbols]
