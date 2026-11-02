"""Data provider factory."""

from src.data.base import MarketDataProvider
from src.data.mock_provider import MockDataProvider


def create_data_provider(
    mode: str,
    api_key: str = "",
    access_token: str = "",
) -> MarketDataProvider:
    if mode == "live" and api_key and access_token:
        try:
            from src.data.kite_provider import KiteDataProvider

            return KiteDataProvider(api_key, access_token)
        except Exception:
            pass
    return MockDataProvider()
