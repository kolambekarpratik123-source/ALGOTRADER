-- Realised profit and win rate by sector (showcase run), joining trades to the stock dimension.
WITH showcase AS (SELECT run_id FROM dim_run WHERE is_showcase = 1 LIMIT 1)
SELECT st.sector,
       COUNT(*)                                   AS closed_trades,
       ROUND(100.0 * AVG(t.pnl > 0), 1)           AS win_rate_pct,
       ROUND(SUM(t.pnl), 0)                       AS total_pnl_rs,
       ROUND(AVG(t.pnl), 0)                       AS avg_pnl_rs,
       ROUND(SUM(t.charges), 0)                   AS sell_charges_rs
FROM fact_trade t
JOIN showcase s  ON s.run_id = t.run_id
JOIN dim_stock st ON st.symbol = t.symbol
WHERE t.side = 'SELL'
GROUP BY st.sector
ORDER BY total_pnl_rs DESC;
