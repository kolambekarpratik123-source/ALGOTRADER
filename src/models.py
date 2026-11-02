from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


@dataclass
class Quote:
    symbol: str
    exchange: str
    ltp: float
    open: float
    high: float
    low: float
    close: float
    volume: int
    timestamp: datetime


@dataclass
class Candle:
    symbol: str
    exchange: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    timestamp: datetime


@dataclass
class Signal:
    symbol: str
    side: Side
    strength: float  # 0.0 to 1.0
    reason: str
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


@dataclass
class Order:
    id: str
    symbol: str
    exchange: str
    side: Side
    quantity: int
    order_type: OrderType
    price: Optional[float]
    status: OrderStatus
    filled_price: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class Position:
    symbol: str
    exchange: str
    quantity: int
    avg_price: float
    stop_loss: float
    take_profit: float
    opened_at: datetime = field(default_factory=datetime.now)

    @property
    def is_long(self) -> bool:
        return self.quantity > 0

    def unrealized_pnl(self, ltp: float) -> float:
        return (ltp - self.avg_price) * self.quantity

    def unrealized_pnl_pct(self, ltp: float) -> float:
        if self.avg_price == 0:
            return 0.0
        return ((ltp - self.avg_price) / self.avg_price) * 100
