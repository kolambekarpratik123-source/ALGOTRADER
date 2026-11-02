"""Trading costs for Indian equity delivery (CNC) trades.

Defaults follow Zerodha's published equity delivery charges as of 2025.
They are approximate: check https://zerodha.com/charges and update if they change.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CostModel:
    brokerage_pct: float = 0.0          # Zerodha delivery brokerage is free
    stt_pct: float = 0.1                # Securities Transaction Tax, on buy and sell
    exchange_txn_pct: float = 0.00297   # NSE transaction charge (BSE is ~0.00375)
    sebi_fee_pct: float = 0.0001        # Rs 10 per crore
    stamp_duty_pct: float = 0.015       # on buy side only
    gst_pct: float = 18.0               # on brokerage + exchange + SEBI fees
    dp_charge_per_sell: float = 15.93   # depository charge per stock sold, incl. GST
    slippage_pct: float = 0.05          # price you actually get vs. the candle price

    def fill_price(self, price: float, is_buy: bool) -> float:
        """Price after slippage: you pay a bit more when buying, get a bit less when selling."""
        s = self.slippage_pct / 100
        return price * (1 + s) if is_buy else price * (1 - s)

    def charges(self, turnover: float, is_buy: bool) -> float:
        """Rupee charges for one order with the given turnover (qty x price)."""
        brokerage = turnover * self.brokerage_pct / 100
        stt = turnover * self.stt_pct / 100
        txn = turnover * self.exchange_txn_pct / 100
        sebi = turnover * self.sebi_fee_pct / 100
        gst = (brokerage + txn + sebi) * self.gst_pct / 100
        stamp = turnover * self.stamp_duty_pct / 100 if is_buy else 0.0
        dp = 0.0 if is_buy else self.dp_charge_per_sell
        return brokerage + stt + txn + sebi + gst + stamp + dp


ZERO_COSTS = CostModel(
    stt_pct=0.0,
    exchange_txn_pct=0.0,
    sebi_fee_pct=0.0,
    stamp_duty_pct=0.0,
    dp_charge_per_sell=0.0,
    slippage_pct=0.0,
)
