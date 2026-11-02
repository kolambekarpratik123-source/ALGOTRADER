-- Does the ranker beat simply holding every stock? Compared on markets WITH a hidden
-- pattern and on pure-noise markets (where any "win" is luck).
SELECT
    data_source,
    market_type,
    COUNT(*)                                             AS runs,
    ROUND(AVG(ic), 4)                                    AS avg_ic,
    ROUND(AVG(total_return_pct), 1)                      AS avg_return_pct,
    ROUND(AVG(benchmark_return_pct), 1)                  AS avg_benchmark_pct,
    SUM(total_return_pct > benchmark_return_pct)         AS runs_beating_benchmark,
    ROUND(MAX(max_drawdown_pct), 1)                      AS worst_drawdown_pct,
    ROUND(AVG(total_costs), 0)                           AS avg_costs_rs
FROM dim_run
GROUP BY data_source, market_type
ORDER BY data_source, market_type;
