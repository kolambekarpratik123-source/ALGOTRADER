from enum import Enum
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TradingMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class Exchange(str, Enum):
    BSE = "BSE"
    NSE = "NSE"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    trading_mode: TradingMode = TradingMode.PAPER
    exchange: Exchange = Exchange.BSE

    kite_api_key: str = ""
    kite_api_secret: str = ""
    kite_access_token: str = ""

    initial_capital: float = 100_000.0
    max_position_size_pct: float = 10.0
    max_daily_loss_pct: float = 2.0
    max_open_positions: int = 5
    default_stop_loss_pct: float = 1.5
    default_take_profit_pct: float = 3.0

    strategy: str = "ma_crossover"
    watchlist: str = "RELIANCE,TCS,INFY"

    @property
    def symbols(self) -> list[str]:
        return [s.strip().upper() for s in self.watchlist.split(",") if s.strip()]


def get_settings() -> Settings:
    return Settings()
