"""Live Zerodha Kite execution provider."""

import asyncio
from datetime import datetime

from src.models import Order, OrderStatus, OrderType, Side


class KiteExecutor:
    """Real order execution via Zerodha Kite Connect REST API."""

    def __init__(self, api_key: str, access_token: str) -> None:
        self.api_key = api_key
        self.access_token = access_token
        self._kite = None

    def _get_kite(self):
        if not self._kite:
            try:
                from kiteconnect import KiteConnect

                self._kite = KiteConnect(api_key=self.api_key)
                self._kite.set_access_token(self.access_token)
            except ImportError as exc:
                raise ImportError("Install kiteconnect: pip install kiteconnect") from exc
        return self._kite

    async def place_order(
        self,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        price: float | None = None,
    ) -> Order:
        kite = self._get_kite()
        transaction_type = (
            kite.TRANSACTION_TYPE_BUY if side == Side.BUY else kite.TRANSACTION_TYPE_SELL
        )
        k_order_type = (
            kite.ORDER_TYPE_MARKET if order_type == OrderType.MARKET else kite.ORDER_TYPE_LIMIT
        )

        loop = asyncio.get_event_loop()
        order_id = await loop.run_in_executor(
            None,
            lambda: kite.place_order(
                variety=kite.VARIETY_REGULAR,
                exchange=exchange,
                tradingsymbol=symbol.upper(),
                transaction_type=transaction_type,
                quantity=quantity,
                product=kite.PRODUCT_MIS,
                order_type=k_order_type,
                price=price if order_type == OrderType.LIMIT else None,
            ),
        )

        return Order(
            id=str(order_id),
            symbol=symbol.upper(),
            exchange=exchange,
            side=side,
            quantity=quantity,
            order_type=order_type,
            price=price,
            status=OrderStatus.FILLED,
            timestamp=datetime.now(),
        )
