-- Best and worst 5 stocks by realised profit, ranked with RANK().
WITH showcase AS (SELECT run_id FROM dim_run WHERE is_showcase = 1 LIMIT 1),
by_stock AS (
    SELECT t.symbol, st.sector,
           COUNT(*)        AS closed_trades,
           SUM(t.pnl)      AS total_pnl
    FROM fact_trade t
    JOIN showcase s   ON s.run_id = t.run_id
    JOIN dim_stock st ON st.symbol = t.symbol
    WHERE t.side = 'SELL'
    GROUP BY t.symbol, st.sector
),
ranked AS (
    SELECT *,
           RANK() OVER (ORDER BY total_pnl DESC) AS best_rank,
           RANK() OVER (ORDER BY total_pnl ASC)  AS worst_rank
    FROM by_stock
)
SELECT CASE WHEN best_rank <= 5 THEN 'Top 5' ELSE 'Bottom 5' END AS grp,
       symbol, sector, closed_trades, ROUND(total_pnl, 0) AS total_pnl_rs
FROM ranked
WHERE best_rank <= 5 OR worst_rank <= 5
ORDER BY total_pnl DESC;
