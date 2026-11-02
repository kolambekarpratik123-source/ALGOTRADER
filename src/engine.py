"""Main trading engine — orchestrates data, strategy, risk, and execution."""

from __future__ import annotations

import asyncio
from datetime import datetime

from rich.console import Console
from rich.table import Table

from src.config import Settings, TradingMode
from src.data.base import MarketDataProvider
from src.execution import create_executor
from src.models import OrderType, Position, Quote, Side
from src.risk.manager import RiskManager
from src.storage.state import save_state, save_trades
from src.strategies.registry import get_strategy

console = Console()


class TradingEngine:
    def __init__(
        self,
        settings: Settings,
        data_provider: MarketDataProvider,
        strategy_name: str | None = None,
    ):
        self.settings = settings
        self.data = data_provider
        self.strategy = get_strategy(strategy_name or settings.strategy)
        self.risk = RiskManager(settings)
        self.executor = create_executor(
            settings.trading_mode.value,
            settings.kite_api_key,
            settings.kite_access_token,
        )
        self.positions: list[Position] = []
        self.trade_log: list[dict] = []
        self.quotes: dict[str, Quote] = {}
        self._running = False

    def portfolio_value(self, quotes: dict[str, float] | None = None) -> float:
        q = quotes or {p.symbol: p.avg_price for p in self.positions}
        positions_value = sum(p.quantity * q.get(p.symbol, p.avg_price) for p in self.positions)
        return self.risk.cash + positions_value

    def _persist_state(self) -> None:
        pv = self.portfolio_value(
            {p.symbol: self.quotes[p.symbol].ltp for p in self.positions if p.symbol in self.quotes}
        )
        save_state(
            {
                "mode": self.settings.trading_mode.value,
                "exchange": self.settings.exchange.value,
                "strategy": self.strategy.name,
                "cash": round(self.risk.cash, 2),
                "portfolio_value": round(pv, 2),
                "daily_pnl": round(self.risk.daily_pnl, 2),
                "positions": [
                    {
                        "symbol": p.symbol,
                        "qty": p.quantity,
                        "avg_price": p.avg_price,
                        "stop_loss": p.stop_loss,
                        "take_profit": p.take_profit,
                        "unrealized_pnl": round(
                            p.unrealized_pnl(self.quotes[p.symbol].ltp)
                            if p.symbol in self.quotes
                            else 0,
                            2,
                        ),
                    }
                    for p in self.positions
                ],
                "quotes": {
                    sym: {"ltp": q.ltp, "volume": q.volume, "time": q.timestamp.isoformat()}
                    for sym, q in self.quotes.items()
                },
            }
        )
        save_trades(self.trade_log)

    async def _check_exits(self) -> None:
        for position in list(self.positions):
            quote = await self.data.get_quote(position.symbol, position.exchange)
            if not quote:
                continue
            self.quotes[position.symbol] = quote

            should_exit, reason = self.risk.check_exit(position, quote)
            if should_exit:
                await self._close_position(position, quote.ltp, reason)

    async def _close_position(self, position: Position, price: float, reason: str) -> None:
        await self.executor.place_order(
            symbol=position.symbol,
            exchange=position.exchange,
            side=Side.SELL,
            quantity=abs(position.quantity),
            order_type=OrderType.MARKET,
            price=price,
        )
        proceeds = position.quantity * price
        pnl = position.unrealized_pnl(price)
        self.risk.cash += proceeds

        self.trade_log.append(
            {
                "time": datetime.now().isoformat(),
                "action": "SELL",
                "symbol": position.symbol,
                "qty": position.quantity,
                "price": price,
                "pnl": round(pnl, 2),
                "reason": reason,
            }
        )
        self.positions.remove(position)
        console.print(
            f"[red]EXIT[/red] {position.symbol} x{position.quantity} @ {price} "
            f"| PnL: {pnl:+.2f} | {reason}"
        )

    async def _scan_for_entries(self) -> None:
        for symbol in self.settings.symbols:
            candles = await self.data.get_candles(
                symbol, self.settings.exchange.value, interval="5minute", count=50
            )
            signal = self.strategy.analyze(symbol, candles)
            if not signal or signal.side != Side.BUY:
                continue

            quote = await self.data.get_quote(symbol, self.settings.exchange.value)
            if not quote:
                continue
            self.quotes[symbol] = quote

            portfolio_val = self.portfolio_value({symbol: quote.ltp})
            decision = self.risk.evaluate_entry(signal, quote, self.positions, portfolio_val)

            if not decision.allowed:
                console.print(f"[dim]SKIP {symbol}: {decision.reason}[/dim]")
                continue

            if self.settings.trading_mode == TradingMode.LIVE:
                await self.executor.place_order(
                    symbol=symbol,
                    exchange=self.settings.exchange.value,
                    side=Side.BUY,
                    quantity=decision.quantity,
                    order_type=OrderType.MARKET,
                )
            else:
                order = await self.executor.place_order(
                    symbol=symbol,
                    exchange=self.settings.exchange.value,
                    side=Side.BUY,
                    quantity=decision.quantity,
                    order_type=OrderType.MARKET,
                )
                if hasattr(self.executor, "fill_at_quote"):
                    self.executor.fill_at_quote(order, quote)

            cost = decision.quantity * quote.ltp
            self.risk.cash -= cost

            position = Position(
                symbol=symbol,
                exchange=self.settings.exchange.value,
                quantity=decision.quantity,
                avg_price=quote.ltp,
                stop_loss=decision.stop_loss,
                take_profit=decision.take_profit,
            )
            self.positions.append(position)

            self.trade_log.append(
                {
                    "time": datetime.now().isoformat(),
                    "action": "BUY",
                    "symbol": symbol,
                    "qty": decision.quantity,
                    "price": quote.ltp,
                    "pnl": 0,
                    "reason": signal.reason,
                }
            )
            console.print(
                f"[green]BUY[/green] {symbol} x{decision.quantity} @ {quote.ltp} "
                f"| SL={decision.stop_loss} TP={decision.take_profit} | {signal.reason}"
            )

    async def refresh_quotes(self) -> None:
        for symbol in self.settings.symbols:
            quote = await self.data.get_quote(symbol, self.settings.exchange.value)
            if quote:
                self.quotes[symbol] = quote

    def print_status(self) -> None:
        table = Table(title=f"Portfolio ({self.settings.exchange.value})")
        table.add_column("Symbol")
        table.add_column("Qty", justify="right")
        table.add_column("Avg", justify="right")
        table.add_column("LTP", justify="right")
        table.add_column("SL", justify="right")
        table.add_column("TP", justify="right")

        for p in self.positions:
            ltp = self.quotes.get(p.symbol)
            ltp_str = f"{ltp.ltp:.2f}" if ltp else "—"
            table.add_row(
                p.symbol,
                str(p.quantity),
                f"{p.avg_price:.2f}",
                ltp_str,
                f"{p.stop_loss:.2f}",
                f"{p.take_profit:.2f}",
            )

        console.print(table)
        pv = self.portfolio_value(
            {p.symbol: self.quotes[p.symbol].ltp for p in self.positions if p.symbol in self.quotes}
        )
        console.print(
            f"Cash: {self.risk.cash:,.2f} | Portfolio: {pv:,.2f} "
            f"| Mode: {self.settings.trading_mode.value}"
        )

    async def run_cycle(self) -> None:
        await self.refresh_quotes()
        await self._check_exits()
        await self._scan_for_entries()
        self.print_status()
        self._persist_state()

    async def run(self, interval_seconds: int = 30, max_cycles: int | None = None) -> None:
        await self.data.connect()
        await self.data.subscribe(self.settings.symbols, self.settings.exchange.value)
        self._running = True
        cycle = 0

        console.print(
            f"[bold]Algotrader started[/bold] | Exchange: {self.settings.exchange.value} "
            f"| Strategy: {self.strategy.name} | Mode: {self.settings.trading_mode.value}"
        )

        try:
            while self._running:
                cycle += 1
                console.print(
                    f"\n[bold cyan]--- Cycle {cycle} @ {datetime.now():%H:%M:%S} ---[/bold cyan]"
                )
                await self.run_cycle()

                if max_cycles and cycle >= max_cycles:
                    break
                await asyncio.sleep(interval_seconds)
        finally:
            await self.data.disconnect()
            self._running = False

    def stop(self) -> None:
        self._running = False
