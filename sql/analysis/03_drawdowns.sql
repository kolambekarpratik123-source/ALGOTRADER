-- Worst drawdowns: how far the portfolio fell from its previous peak (showcase run).
-- Running peak via MAX() OVER an expanding window.
WITH showcase AS (SELECT run_id FROM dim_run WHERE is_showcase = 1 LIMIT 1),
curve AS (
    SELECT p.date,
           p.equity,
           MAX(p.equity) OVER (ORDER BY p.date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS peak
    FROM fact_portfolio_daily p
    JOIN showcase s ON s.run_id = p.run_id
)
SELECT date,
       ROUND(equity, 0)                         AS equity,
       ROUND(peak, 0)                           AS previous_peak,
       ROUND(100.0 * (equity - peak) / peak, 2) AS drawdown_pct
FROM curve
ORDER BY drawdown_pct
LIMIT 10;
