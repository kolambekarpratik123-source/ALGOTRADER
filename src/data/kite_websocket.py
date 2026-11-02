"""Kite Ticker WebSocket wrapper for real-time market data streaming."""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime
from typing import Optional

from src.models import Quote


class KiteWebSocket:
    """Wraps KiteTicker for thread-safe live streaming."""

    def __init__(self, api_key: str, access_token: str):
        self.api_key = api_key
        self.access_token = access_token
        self.kws = None
        self._quotes: dict[str, Quote] = {}
        self._token_map: dict[int, tuple[str, str]] = {}
        self._lock = threading.Lock()
        self._connected = False

    def register_instruments(self, token_map: dict[int, tuple[str, str]]) -> None:
        """Map instrument_token -> (symbol, exchange)."""
        with self._lock:
            self._token_map = token_map

    def get_latest(self, symbol: str) -> Optional[Quote]:
        with self._lock:
            return self._quotes.get(symbol.upper())

    async def connect(self, tokens: list[int]) -> None:
        try:
            from kiteconnect import KiteTicker
        except ImportError:
            return

        self.kws = KiteTicker(self.api_key, self.access_token)

        def on_ticks(ws, ticks):
            with self._lock:
                for t in ticks:
                    tok = t.get("instrument_token")
                    if tok in self._token_map:
                        sym, exch = self._token_map[tok]
                        ltp = float(t.get("last_price", 0))
                        ohlc = t.get("ohlc", {})
                        self._quotes[sym] = Quote(
                            symbol=sym,
                            exchange=exch,
                            ltp=ltp,
                            open=float(ohlc.get("open", 0)),
                            high=float(ohlc.get("high", 0)),
                            low=float(ohlc.get("low", 0)),
                            close=float(ohlc.get("close", 0)),
                            volume=int(t.get("volume", 0)),
                            timestamp=datetime.now(),
                        )

        def on_connect(ws, response):
            self._connected = True
            ws.subscribe(tokens)
            ws.set_mode(ws.MODE_FULL, tokens)

        def on_close(ws, code, reason):
            self._connected = False

        self.kws.on_ticks = on_ticks
        self.kws.on_connect = on_connect
        self.kws.on_close = on_close

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.kws.connect, True)

    async def disconnect(self) -> None:
        if self.kws and self._connected:
            self.kws.close()
        self._connected = False
