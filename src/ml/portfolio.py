"""Turn rankings into trades: every few days hold the top-ranked stocks, after real costs."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.backtest.costs import CostModel


@dataclass
class PortfolioResult:
    total_return_pct: float
    benchmark_return_pct: float
    cagr_pct: float
    benchmark_cagr_pct: float
    max_drawdown_pct: float
    benchmark_max_drawdown_pct: float
    sharpe: float
    benchmark_sharpe: float
    total_costs: float
    trades: int
    worst_month_pct: float
    equity: pd.Series = field(repr=False, default=None)
    benchmark: pd.Series = field(repr=False, default=None)
    trade_log: list = field(repr=False, default_factory=list)

    def to_dict(self) -> dict:
        d = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in self.__dict__.items()
             if k not in ("equity", "benchmark", "trade_log")}
        d["equity_curve"] = [
            {"date": str(i.date()), "equity": round(float(v), 2), "benchmark": round(float(b), 2)}
            for i, v, b in zip(self.equity.index, self.equity.values, self.benchmark.values)
        ]
        return d


def _stats(eq: pd.Series) -> tuple[float, float, float]:
    rets = eq.pct_change().dropna()
    years = max(len(eq) / 252, 1e-9)
    cagr = ((eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1) * 100
    dd = float(((eq.cummax() - eq) / eq.cummax()).max() * 100)
    sharpe = float(rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0.0
    return cagr, dd, sharpe


def simulate_top_k(
    preds: pd.DataFrame,
    market: dict[str, pd.DataFrame],
    top_k: int = 10,
    rebalance_days: int = 5,
    capital: float = 100_000.0,
    costs: CostModel | None = None,
    max_monthly_loss_pct: float | None = None,
    hold_buffer: float = 1.0,
) -> PortfolioResult:
    """Every `rebalance_days`, pick the top_k stocks by prediction at the close and trade at
    the next open. Stocks that stay in the top_k are kept (no trading cost). Stocks that drop
    out are sold; the cash is split equally among the new entries.

    If max_monthly_loss_pct is set, the portfolio goes to cash for the rest of the calendar
    month once that month's loss reaches the limit.
    """
    costs = costs or CostModel()
    opn, close = market["open"], market["close"]
    test_dates = preds.index.get_level_values("date").unique().sort_values()
    all_dates = close.index
    start_i = all_dates.get_loc(test_dates[0])
    end_i = all_dates.get_loc(test_dates[-1])
    pred_wide = preds["pred"].unstack("symbol")

    cash = capital
    holdings: dict[str, int] = {}
    total_costs = 0.0
    n_trades = 0
    pending_target: list[str] | None = None
    equity = {}
    month_start_value = capital
    current_month = None
    halted = False
    trade_log: list[dict] = []
    cost_basis: dict[str, float] = {}  # rupees paid to open each holding, incl. charges
    current_day = None

    def sell(sym: str, price: float, reason: str) -> None:
        nonlocal cash, total_costs, n_trades
        qty = holdings[sym]
        px = costs.fill_price(price, is_buy=False)
        fee = costs.charges(px * qty, is_buy=False)
        cash += px * qty - fee
        total_costs += fee
        n_trades += 1
        trade_log.append({
            "date": current_day, "symbol": sym, "side": "SELL", "quantity": qty,
            "price": round(px, 2), "value": round(px * qty, 2), "charges": round(fee, 2),
            "pnl": round(px * qty - fee - cost_basis.pop(sym, 0.0), 2), "reason": reason,
        })
        del holdings[sym]

    for step, i in enumerate(range(start_i, end_i + 1)):
        d = all_dates[i]
        current_day = d
        value_at_open = cash + sum(q * opn.at[d, s] for s, q in holdings.items())

        # monthly loss limit
        if (d.year, d.month) != current_month:
            current_month = (d.year, d.month)
            month_start_value = value_at_open
            halted = False
        if max_monthly_loss_pct is not None and not halted:
            if value_at_open <= month_start_value * (1 - max_monthly_loss_pct / 100):
                halted = True
                for s in list(holdings):
                    sell(s, opn.at[d, s], "Monthly loss limit")
                pending_target = None

        # trade yesterday's decision at today's open
        if pending_target is not None and not halted:
            for s in [s for s in holdings if s not in pending_target]:
                sell(s, opn.at[d, s], "Dropped out of top ranks")
            new = [s for s in pending_target if s not in holdings]
            if new:
                per_stock = cash / len(new)
                for s in new:
                    px = costs.fill_price(opn.at[d, s], is_buy=True)
                    qty = int(per_stock / (px * (1 + 0.002)))  # leave room for charges
                    if qty < 1:
                        continue
                    fee = costs.charges(px * qty, is_buy=True)
                    if px * qty + fee > cash:
                        continue
                    cash -= px * qty + fee
                    total_costs += fee
                    n_trades += 1
                    holdings[s] = qty
                    cost_basis[s] = px * qty + fee
                    trade_log.append({
                        "date": d, "symbol": s, "side": "BUY", "quantity": qty,
                        "price": round(px, 2), "value": round(px * qty, 2), "charges": round(fee, 2),
                        "pnl": 0.0, "reason": "Entered top ranks",
                    })
            pending_target = None

        # decide at today's close
        if step % rebalance_days == 0 and d in pred_wide.index and not halted:
            row = pred_wide.loc[d].dropna()
            ranked = list(row.sort_values(ascending=False).index)
            keep_zone = set(ranked[: int(top_k * hold_buffer)])
            kept = [s for s in holdings if s in keep_zone]
            fill = [s for s in ranked if s not in kept][: max(0, top_k - len(kept))]
            pending_target = kept + fill

        equity[d] = cash + sum(q * close.at[d, s] for s, q in holdings.items())

    eq = pd.Series(equity)

    # Benchmark: equal money in every stock on day one, hold to the end, same costs
    d0 = all_dates[start_i]
    syms = list(close.columns)
    per = capital / len(syms)
    bench_cash = capital
    bench_q = {}
    for s in syms:
        px = costs.fill_price(opn.at[d0, s], is_buy=True)
        q = int(per / (px * 1.002))
        if q > 0:
            bench_cash -= px * q + costs.charges(px * q, True)
            bench_q[s] = q
    bench = close.iloc[start_i : end_i + 1][list(bench_q)].mul(pd.Series(bench_q)).sum(axis=1) + bench_cash
    # charge the exit on the last day so both sides pay to get out
    last = all_dates[end_i]
    exit_fee = sum(
        costs.charges(costs.fill_price(close.at[last, s], False) * q, False)
        + close.at[last, s] * q * costs.slippage_pct / 100
        for s, q in bench_q.items()
    )
    bench.iloc[-1] -= exit_fee

    # final exit for the strategy too
    final_value = cash
    for s, q in holdings.items():
        px = costs.fill_price(close.at[last, s], is_buy=False)
        fee = costs.charges(px * q, is_buy=False)
        final_value += px * q - fee
        total_costs += fee
        trade_log.append({
            "date": last, "symbol": s, "side": "SELL", "quantity": q,
            "price": round(px, 2), "value": round(px * q, 2), "charges": round(fee, 2),
            "pnl": round(px * q - fee - cost_basis.pop(s, 0.0), 2), "reason": "End of test",
        })
    eq.iloc[-1] = final_value

    month_ends = eq.resample("ME").last()
    monthly = pd.concat([pd.Series([capital]), month_ends.reset_index(drop=True)]).pct_change().dropna()
    cagr, dd, sh = _stats(eq)
    bcagr, bdd, bsh = _stats(bench)
    return PortfolioResult(
        total_return_pct=(eq.iloc[-1] / capital - 1) * 100,
        benchmark_return_pct=(bench.iloc[-1] / capital - 1) * 100,
        cagr_pct=cagr,
        benchmark_cagr_pct=bcagr,
        max_drawdown_pct=dd,
        benchmark_max_drawdown_pct=bdd,
        sharpe=sh,
        benchmark_sharpe=bsh,
        total_costs=total_costs,
        trades=n_trades,
        worst_month_pct=float(monthly.min() * 100) if len(monthly) else 0.0,
        equity=eq,
        benchmark=bench,
        trade_log=trade_log,
    )
