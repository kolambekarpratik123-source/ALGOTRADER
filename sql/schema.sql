-- Algotrader reporting database (SQLite).
-- Star schema: dimension tables (dim_*) describe things, fact tables (fact_*) record events.
-- Every fact row carries run_id, and every run records its data_source ('synthetic' or 'nse'),
-- so real market data can be loaded later without changing this schema.

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS fact_strategy_backtest;
DROP TABLE IF EXISTS fact_portfolio_daily;
DROP TABLE IF EXISTS fact_trade;
DROP TABLE IF EXISTS fact_prediction;
DROP TABLE IF EXISTS fact_price;
DROP TABLE IF EXISTS dim_stock;
DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS dim_run;

-- One row per test run: one market (real, or one synthetic seed) run through the ranker.
CREATE TABLE dim_run (
    run_id               INTEGER PRIMARY KEY,
    created_at           TEXT    NOT NULL,
    data_source          TEXT    NOT NULL CHECK (data_source IN ('synthetic', 'nse', 'bse')),
    market_type          TEXT    NOT NULL,          -- 'pattern', 'noise' or 'real'
    seed                 INTEGER,
    signal_strength      REAL,
    is_showcase          INTEGER NOT NULL DEFAULT 0, -- 1 = prices and predictions stored in detail
    top_k                INTEGER NOT NULL,
    rebalance_days       INTEGER NOT NULL,
    horizon_days         INTEGER NOT NULL,
    initial_capital      REAL    NOT NULL,
    ic                   REAL,
    ic_tstat             REAL,
    total_return_pct     REAL,
    benchmark_return_pct REAL,
    cagr_pct             REAL,
    max_drawdown_pct     REAL,
    sharpe               REAL,
    worst_month_pct      REAL,
    total_costs          REAL,
    trade_count          INTEGER
);

CREATE TABLE dim_date (
    date         TEXT PRIMARY KEY,   -- YYYY-MM-DD
    year         INTEGER NOT NULL,
    quarter      INTEGER NOT NULL,
    month        INTEGER NOT NULL,
    month_name   TEXT    NOT NULL,
    year_month   TEXT    NOT NULL,   -- YYYY-MM
    week_of_year INTEGER NOT NULL,
    weekday_name TEXT    NOT NULL
);

CREATE TABLE dim_stock (
    symbol       TEXT PRIMARY KEY,
    company_name TEXT NOT NULL,
    sector       TEXT NOT NULL,
    data_source  TEXT NOT NULL
);

CREATE TABLE fact_price (
    run_id  INTEGER NOT NULL REFERENCES dim_run(run_id),
    date    TEXT    NOT NULL REFERENCES dim_date(date),
    symbol  TEXT    NOT NULL REFERENCES dim_stock(symbol),
    open    REAL, high REAL, low REAL, close REAL, volume INTEGER,
    PRIMARY KEY (run_id, date, symbol)
);

-- Out-of-sample model scores: what the ranker predicted, and what actually happened.
CREATE TABLE fact_prediction (
    run_id        INTEGER NOT NULL REFERENCES dim_run(run_id),
    date          TEXT    NOT NULL REFERENCES dim_date(date),
    symbol        TEXT    NOT NULL REFERENCES dim_stock(symbol),
    score         REAL    NOT NULL,
    rank_in_day   INTEGER NOT NULL,   -- 1 = most attractive stock that day
    fwd_return    REAL,               -- actual return over the prediction horizon
    fold          INTEGER NOT NULL,   -- walk-forward fold the prediction came from
    PRIMARY KEY (run_id, date, symbol)
);

CREATE TABLE fact_trade (
    trade_id  INTEGER PRIMARY KEY,
    run_id    INTEGER NOT NULL REFERENCES dim_run(run_id),
    date      TEXT    NOT NULL REFERENCES dim_date(date),
    symbol    TEXT    NOT NULL REFERENCES dim_stock(symbol),
    side      TEXT    NOT NULL CHECK (side IN ('BUY', 'SELL')),
    quantity  INTEGER NOT NULL,
    price     REAL    NOT NULL,
    value     REAL    NOT NULL,
    charges   REAL    NOT NULL,
    pnl       REAL    NOT NULL,       -- realised profit after all charges (SELL rows only)
    reason    TEXT
);

CREATE TABLE fact_portfolio_daily (
    run_id           INTEGER NOT NULL REFERENCES dim_run(run_id),
    date             TEXT    NOT NULL REFERENCES dim_date(date),
    equity           REAL    NOT NULL,
    benchmark_equity REAL    NOT NULL,
    PRIMARY KEY (run_id, date)
);

-- Single-stock rule-based strategies (MA crossover, RSI, MACD, composite) from `main.py baseline`.
CREATE TABLE fact_strategy_backtest (
    data_source         TEXT NOT NULL,
    strategy            TEXT NOT NULL,
    symbol              TEXT NOT NULL,
    period_start        TEXT,
    period_end          TEXT,
    total_return_pct    REAL,
    buy_hold_return_pct REAL,
    trade_count         INTEGER,
    win_rate_pct        REAL,
    max_drawdown_pct    REAL,
    sharpe              REAL,
    total_costs         REAL,
    PRIMARY KEY (data_source, strategy, symbol)
);

CREATE INDEX idx_trade_run_date ON fact_trade(run_id, date);
CREATE INDEX idx_pred_run_rank  ON fact_prediction(run_id, rank_in_day);
