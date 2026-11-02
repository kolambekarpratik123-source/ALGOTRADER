"""Paper trading execution — simulated instant fills."""

import uuid
from datetime import datetime

from src.models import Order, OrderStatus, OrderType, Quote, Side


class PaperExecutor:
    """Simulated execution engine for paper trading."""

    async def place_order(
        self,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        price: float | None = None,
    ) -> Order:
        order_id = f"PAPER-{uuid.uuid4().hex[:8].upper()}"
        return Order(
            id=order_id,
            symbol=symbol.upper(),
            exchange=exchange,
            side=side,
            quantity=quantity,
            order_type=order_type,
            price=price,
            status=OrderStatus.FILLED,
            filled_price=price,
            timestamp=datetime.now(),
        )

    def fill_at_quote(self, order: Order, quote: Quote) -> Order:
        order.filled_price = quote.ltp
        order.status = OrderStatus.FILLED
        return order
