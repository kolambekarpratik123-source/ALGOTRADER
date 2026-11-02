-- How much trading costs took out of profits, per year (showcase run).
-- charges_pct_of_gross_pnl is only shown for years with a gross profit (otherwise it's meaningless).
WITH showcase AS (SELECT run_id FROM dim_run WHERE is_showcase = 1 LIMIT 1),
yearly AS (
    SELECT d.year,
           SUM(t.side = 'BUY')                                  AS buys,
           SUM(t.side = 'SELL')                                 AS sells,
           SUM(t.charges)                                       AS charges,
           SUM(CASE WHEN t.side = 'SELL' THEN t.pnl ELSE 0 END) AS net_pnl
    FROM fact_trade t
    JOIN showcase s ON s.run_id = t.run_id
    JOIN dim_date d ON d.date = t.date
    GROUP BY d.year
)
SELECT year, buys, sells,
       ROUND(charges, 0)                  AS charges_rs,
       ROUND(net_pnl + charges, 0)        AS gross_pnl_rs,
       ROUND(net_pnl, 0)                  AS net_realised_pnl_rs,
       CASE WHEN net_pnl + charges > 0
            THEN ROUND(100.0 * charges / (net_pnl + charges), 1) END AS charges_pct_of_gross_pnl
FROM yearly
ORDER BY year;
