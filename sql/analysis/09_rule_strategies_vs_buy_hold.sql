-- The old rule-based strategies (from `main.py baseline`) vs. buy-and-hold, per strategy.
SELECT data_source,
       strategy,
       COUNT(*)                                        AS symbols,
       ROUND(AVG(total_return_pct), 1)                 AS avg_return_pct,
       ROUND(AVG(buy_hold_return_pct), 1)              AS avg_buy_hold_pct,
       SUM(total_return_pct > buy_hold_return_pct)     AS beat_buy_hold,
       ROUND(AVG(win_rate_pct), 1)                     AS avg_win_rate_pct,
       SUM(trade_count)                                AS trades
FROM fact_strategy_backtest
GROUP BY data_source, strategy
ORDER BY avg_return_pct DESC;
