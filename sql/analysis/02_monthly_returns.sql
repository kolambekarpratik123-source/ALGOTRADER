-- Monthly return of the ranker vs. the hold-everything benchmark (showcase run).
-- Uses a CTE to find month-end values and LAG() to compare with the previous month.
WITH showcase AS (
    SELECT run_id, initial_capital FROM dim_run WHERE is_showcase = 1 LIMIT 1
),
month_end AS (
    SELECT d.year_month,
           p.equity,
           p.benchmark_equity,
           ROW_NUMBER() OVER (PARTITION BY d.year_month ORDER BY p.date DESC) AS rn
    FROM fact_portfolio_daily p
    JOIN showcase s   ON s.run_id = p.run_id
    JOIN dim_date d   ON d.date = p.date
)
SELECT
    year_month,
    ROUND(equity, 0) AS month_end_equity,
    ROUND(100.0 * (equity / LAG(equity, 1, (SELECT initial_capital FROM showcase))
                   OVER (ORDER BY year_month) - 1), 2) AS ranker_return_pct,
    ROUND(100.0 * (benchmark_equity / LAG(benchmark_equity, 1, (SELECT initial_capital FROM showcase))
                   OVER (ORDER BY year_month) - 1), 2) AS benchmark_return_pct
FROM month_end
WHERE rn = 1
ORDER BY year_month;
