-- The key model check: split each day's predictions into 10 buckets by score.
-- If the model works, average actual return should rise from decile 1 (worst) to 10 (best).
WITH showcase AS (SELECT run_id FROM dim_run WHERE is_showcase = 1 LIMIT 1),
bucketed AS (
    SELECT p.fwd_return,
           NTILE(10) OVER (PARTITION BY p.date ORDER BY p.score) AS decile
    FROM fact_prediction p
    JOIN showcase s ON s.run_id = p.run_id
    WHERE p.fwd_return IS NOT NULL
)
SELECT decile,
       COUNT(*)                          AS predictions,
       ROUND(100.0 * AVG(fwd_return), 3) AS avg_actual_return_pct,
       ROUND(100.0 * AVG(fwd_return > 0), 1) AS pct_positive
FROM bucketed
GROUP BY decile
ORDER BY decile;
