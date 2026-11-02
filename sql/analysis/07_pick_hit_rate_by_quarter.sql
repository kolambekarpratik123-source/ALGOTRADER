-- How often did the top-10 picks beat that day's median stock? By quarter.
-- 50% = no better than a coin flip.
WITH showcase AS (SELECT run_id FROM dim_run WHERE is_showcase = 1 LIMIT 1),
scored AS (
    SELECT p.date, p.rank_in_day, p.fwd_return,
           PERCENT_RANK() OVER (PARTITION BY p.date ORDER BY p.fwd_return) AS return_pct_rank
    FROM fact_prediction p
    JOIN showcase s ON s.run_id = p.run_id
    WHERE p.fwd_return IS NOT NULL
)
SELECT d.year || '-Q' || d.quarter                  AS quarter,
       COUNT(*)                                     AS top10_picks,
       ROUND(100.0 * AVG(return_pct_rank > 0.5), 1) AS beat_median_pct
FROM scored sc
JOIN dim_date d ON d.date = sc.date
WHERE sc.rank_in_day <= (SELECT top_k FROM dim_run WHERE is_showcase = 1 LIMIT 1)
GROUP BY d.year, d.quarter
ORDER BY d.year, d.quarter;
