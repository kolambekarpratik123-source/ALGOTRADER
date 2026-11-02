"""Mock data provider simulating BSE/NSE real-time quotes and historical candles."""

import random
from datetime import datetime, timedelta
from typing import Optional

from src.data.base import MarketDataProvider
from src.models import Candle, Quote

SEED_PRICES: dict[str, float] = {
    # Nifty 50
    "RELIANCE": 2450.0, "TCS": 3850.0, "HDFCBANK": 1680.0, "INFY": 1580.0,
    "ICICIBANK": 1120.0, "HINDUNILVR": 2580.0, "ITC": 465.0, "SBIN": 780.0,
    "BHARTIARTL": 1520.0, "KOTAKBANK": 1860.0, "LT": 3400.0, "AXISBANK": 1190.0,
    "ASIANPAINT": 2950.0, "MARUTI": 10800.0, "SUNPHARMA": 1650.0,
    "TITAN": 3600.0, "NESTLEIND": 24500.0, "ULTRATECH": 10200.0,
    "BAJFINANCE": 7200.0, "WIPRO": 470.0, "POWERGRID": 325.0, "NTPC": 380.0,
    "M&M": 2800.0, "TATAMOTORS": 980.0, "ONGC": 280.0, "JSWSTEEL": 950.0,
    "TATASTEEL": 165.0, "ADANIENT": 2800.0, "ADANIPORTS": 1350.0,
    "BAJAJFINSV": 1620.0, "GRASIM": 2700.0, "HCLTECH": 1720.0,
    "DIVISLAB": 5400.0, "DRREDDY": 6800.0, "EICHERMOT": 4900.0,
    "APOLLOHOSP": 6900.0, "CIPLA": 1580.0, "COALINDIA": 490.0,
    "TATACONSUM": 1100.0, "BPCL": 335.0, "HEROMOTOCO": 5200.0,
    "HINDALCO": 680.0, "INDUSINDBK": 1420.0, "SBILIFE": 1680.0,
    "HDFCLIFE": 760.0, "ICICIPRULI": 720.0, "BRITANNIA": 5600.0,
    "TECHM": 1480.0, "UPL": 540.0,
    # Mid-caps & Next 50
    "MUTHOOTFIN": 1980.0, "COFORGE": 8200.0, "PERSISTENT": 5800.0,
    "LTIM": 5500.0, "MPHASIS": 2800.0, "OFSS": 9800.0, "KPITTECH": 1650.0,
    "TATAELXSI": 7400.0, "ZOMATO": 220.0, "NYKAA": 165.0, "PAYTM": 490.0,
    "POLICYBZR": 700.0, "DMART": 4800.0, "IRCTC": 860.0, "IRFC": 160.0,
    "RVNL": 350.0, "HAL": 4200.0, "BEL": 280.0, "MAZAGON": 5200.0,
    "COCHINSHIP": 2200.0,
    # Banking & Financials
    "BANDHANBNK": 220.0, "IDFCFIRSTB": 75.0, "FEDERALBNK": 180.0,
    "CANBK": 110.0, "BANKBARODA": 275.0, "PNB": 125.0, "RBLBANK": 210.0,
    "AUBANK": 680.0,
    # Auto & Infra
    "ASHOKLEY": 220.0, "TVSMOTOR": 2600.0, "BAJAJ_AUTO": 9200.0,
    "MOTHERSON": 120.0, "MRF": 130000.0, "POLYCAB": 6800.0,
    "HAVELLS": 1820.0, "VOLTAS": 1250.0,
    # Pharma
    "BIOCON": 280.0, "AUROPHARMA": 1200.0, "GLENMARK": 1100.0,
    "LUPIN": 2100.0, "TORNTPHARM": 2800.0, "ALKEM": 5400.0, "IPCALAB": 1350.0,
    # FMCG & Retail
    "GODREJCP": 1350.0, "MARICO": 620.0, "DABUR": 580.0, "EMAMILTD": 780.0,
    "COLPAL": 3200.0, "PGHH": 16500.0,
    # Energy & Power
    "ADANIGREEN": 1800.0, "TATAPOWER": 440.0, "JSW_ENERGY": 520.0,
    "NHPC": 95.0, "SJVN": 130.0, "RECLTD": 520.0, "PFC": 430.0,
    # Chemicals & Materials
    "PIIND": 4200.0, "SRF": 2800.0, "DEEPAKNTR": 2600.0, "AARTI_IND": 580.0,
    "CLEAN": 1650.0, "ASTRAL": 2200.0, "SUPREMEIND": 5400.0,
}


class MockDataProvider(MarketDataProvider):
    def __init__(self) -> None:
        self._prices: dict[str, float] = {}

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    def _get_price(self, symbol: str) -> float:
        sym = symbol.upper()
        if sym not in self._prices:
            self._prices[sym] = SEED_PRICES.get(sym, 1000.0)

        seed = SEED_PRICES.get(sym, 1000.0)
        # Random walk ±0.3%
        change = random.uniform(-0.003, 0.003)
        new_price = self._prices[sym] * (1 + change)
        # Clamp within ±20% of seed
        min_p = seed * 0.8
        max_p = seed * 1.2
        self._prices[sym] = max(min_p, min(max_p, new_price))
        return round(self._prices[sym], 2)

    async def get_quote(self, symbol: str, exchange: str) -> Optional[Quote]:
        ltp = self._get_price(symbol)
        spread = ltp * 0.005
        return Quote(
            symbol=symbol.upper(),
            exchange=exchange,
            ltp=ltp,
            open=round(ltp - spread, 2),
            high=round(ltp + spread, 2),
            low=round(ltp - spread * 1.5, 2),
            close=round(ltp - spread * 0.2, 2),
            volume=random.randint(1000, 50000),
            timestamp=datetime.now(),
        )

    async def get_candles(
        self,
        symbol: str,
        exchange: str,
        interval: str = "5minute",
        count: int = 100,
    ) -> list[Candle]:
        sym = symbol.upper()
        seed = SEED_PRICES.get(sym, 1000.0)
        now = datetime.now()
        candles: list[Candle] = []

        price = seed * 0.95
        for i in range(count):
            ts = now - timedelta(minutes=5 * (count - i))
            change = random.uniform(-0.008, 0.01)
            open_p = price
            close_p = price * (1 + change)
            high_p = max(open_p, close_p) * (1 + random.uniform(0, 0.004))
            low_p = min(open_p, close_p) * (1 - random.uniform(0, 0.004))
            vol = random.randint(500, 20000)

            candles.append(
                Candle(
                    symbol=sym,
                    exchange=exchange,
                    open=round(open_p, 2),
                    high=round(high_p, 2),
                    low=round(low_p, 2),
                    close=round(close_p, 2),
                    volume=vol,
                    timestamp=ts,
                )
            )
            price = close_p

        return candles

    async def subscribe(self, symbols: list[str], exchange: str) -> None:
        pass
