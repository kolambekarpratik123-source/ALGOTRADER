# Power BI dashboard

## Quick start: open the ready-made project

The dashboard is already generated as a Power BI Project in `powerbi/Algotrader/`.

1. On your PC, in the Algotrader folder: `python main.py report`
   (creates the CSVs and regenerates the project with your folder path).
2. Older Power BI Desktop versions only: **File → Options and settings → Options → Preview features** →
   tick **Power BI Project (.pbip) save option** → restart Power BI Desktop.
3. **File → Open** → `powerbi/Algotrader/Algotrader.pbip`.
4. If you get a file-not-found error: **Transform data → Edit parameters → DataFolder**,
   set it to your `...\data\exports\` folder (keep the trailing backslash), then **Refresh**.
5. **File → Save as** → `Algotrader.pbix` if you want a single file to share.

**Theme file (one-time).** The report is written in Power BI's newer PBIR format, which needs Power BI's
base theme file next to it. Desktop ships that file but the generator can't create it. If the pages crash
with "Failed to load the report", save any report from Power BI Desktop as `.pbip`, copy its
`StaticResources/SharedResources/BaseThemes/*.json` into `powerbi/base_theme/`, and run step 1 again.
Tested on Power BI Desktop 2.159 (October 2026).

It has 5 pages (Overview, Monthly, Model check, Trades, Rule strategies), 7 tables,
8 relationships and 22 DAX measures. The rest of this guide explains how it is built,
so you can rebuild or explain it in an interview.

---

## Build it yourself (what the generated project contains)

Build time: about 45–60 minutes in Power BI Desktop (free, Windows).
Data: the CSV files in `data/exports/`, created by `python main.py report`.

> Every number here comes from **synthetic** markets until real NSE data is loaded.
> Put that on the dashboard (a text box on page 1) so nobody mistakes it for real returns.

---

## 1. Load the data

1. Run `python main.py report`. This creates `data/algotrader.db`, `data/exports/*.csv` and the Excel report.
2. In Power BI Desktop: **Home → Get data → Text/CSV**, and load each file in `data/exports/`:
   `dim_run`, `dim_date`, `dim_stock`, `fact_portfolio_daily`, `fact_trade`, `fact_prediction`, `fact_strategy_backtest`.
   (Skip `fact_price` unless you want price charts: it's the biggest file.)
3. In **Transform data**, set types:
   - every `date` column → **Date**
   - money and % columns → **Decimal number**
   - `run_id`, `quantity`, `rank_in_day`, `fold` → **Whole number**
4. **Close & Apply**.

Alternative: connect straight to `data/algotrader.db` with the free SQLite ODBC driver
(Get data → ODBC). CSV is simpler and works everywhere, so use it unless you want refresh-from-DB.

## 2. Data model (Model view)

Star schema. Create these relationships (all single direction, many-to-one):

| From (many) | To (one) |
|---|---|
| `fact_portfolio_daily[date]` | `dim_date[date]` |
| `fact_trade[date]` | `dim_date[date]` |
| `fact_prediction[date]` | `dim_date[date]` |
| `fact_trade[symbol]` | `dim_stock[symbol]` |
| `fact_prediction[symbol]` | `dim_stock[symbol]` |
| `fact_portfolio_daily[run_id]` | `dim_run[run_id]` |
| `fact_trade[run_id]` | `dim_run[run_id]` |
| `fact_prediction[run_id]` | `dim_run[run_id]` |

Then: right-click `dim_date` → **Mark as date table** → `date`.
Sort `dim_date[month_name]` by `dim_date[month]` (Column tools → Sort by column).

## 3. DAX measures

Create a blank table called `_Measures` (Enter data → empty) and add these:

```DAX
Ending Equity =
VAR LastDate = MAX ( fact_portfolio_daily[date] )
RETURN CALCULATE ( SUM ( fact_portfolio_daily[equity] ), fact_portfolio_daily[date] = LastDate )

Ending Benchmark =
VAR LastDate = MAX ( fact_portfolio_daily[date] )
RETURN CALCULATE ( SUM ( fact_portfolio_daily[benchmark_equity] ), fact_portfolio_daily[date] = LastDate )

Starting Capital = MAX ( dim_run[initial_capital] )

Total Return % = DIVIDE ( [Ending Equity], [Starting Capital] ) - 1

Benchmark Return % = DIVIDE ( [Ending Benchmark], [Starting Capital] ) - 1

Excess Return % = [Total Return %] - [Benchmark Return %]

Running Peak =
VAR d = MAX ( fact_portfolio_daily[date] )
RETURN CALCULATE ( MAX ( fact_portfolio_daily[equity] ),
                   FILTER ( ALL ( dim_date ), dim_date[date] <= d ) )

Drawdown % = DIVIDE ( [Ending Equity], [Running Peak] ) - 1

Realised P&L = CALCULATE ( SUM ( fact_trade[pnl] ), fact_trade[side] = "SELL" )

Trading Costs = SUM ( fact_trade[charges] )

Closed Trades = CALCULATE ( COUNTROWS ( fact_trade ), fact_trade[side] = "SELL" )

Win Rate % =
DIVIDE ( CALCULATE ( COUNTROWS ( fact_trade ), fact_trade[side] = "SELL", fact_trade[pnl] > 0 ),
         [Closed Trades] )

Avg Model IC = AVERAGE ( dim_run[ic] )

Avg Actual Return (Top Picks) =
CALCULATE ( AVERAGE ( fact_prediction[fwd_return] ),
            fact_prediction[rank_in_day] <= MAX ( dim_run[top_k] ) )

Avg Actual Return (All Stocks) = AVERAGE ( fact_prediction[fwd_return] )

Pick Edge % = [Avg Actual Return (Top Picks)] - [Avg Actual Return (All Stocks)]

Monthly Return % =
VAR MonthEnd = MAX ( fact_portfolio_daily[date] )
VAR PrevMonthEnd = CALCULATE ( MAX ( fact_portfolio_daily[date] ),
                               FILTER ( ALL ( dim_date ), dim_date[date] < MIN ( dim_date[date] ) ) )
VAR EndVal  = CALCULATE ( SUM ( fact_portfolio_daily[equity] ), fact_portfolio_daily[date] = MonthEnd )
VAR PrevVal = CALCULATE ( SUM ( fact_portfolio_daily[equity] ),
                          ALL ( dim_date ), fact_portfolio_daily[date] = PrevMonthEnd )
RETURN DIVIDE ( EndVal, COALESCE ( PrevVal, [Starting Capital] ) ) - 1
```

Format the `%` measures as Percentage, the rupee ones as Whole number with thousands separator.

## 4. Report pages

**Page 1: Overview**
- Slicer: `dim_run[run_id]` (single select; default to the run where `is_showcase` = 1).
- Cards: Total Return %, Benchmark Return %, Excess Return %, Drawdown % (min), Avg Model IC, Trading Costs.
- Line chart: X = `dim_date[date]`, Y = `fact_portfolio_daily[equity]` and `[benchmark_equity]`.
- Text box: "Synthetic data. Demonstrates the method, not real profit."

**Page 2: Monthly performance**
- Matrix: Rows = `dim_date[year]`, Columns = `dim_date[month_name]`, Values = Monthly Return %.
  Conditional formatting → Background colour → diverging red/white/green, centre 0.
- Area chart: Drawdown % over `dim_date[date]`.

**Page 3: Does the model work?**
- Clustered column: X = `dim_run[market_type]`, Y = Avg Model IC. (Pattern should be clearly above noise.)
- Scatter: X = `dim_run[ic]`, Y = `dim_run[total_return_pct]`, legend = `market_type`.
- Card: Pick Edge %.
- Line chart: X = `dim_date[year_month]`, Y = Pick Edge %.

**Page 4: Trades & sectors**
- Bar chart: `dim_stock[sector]` by Realised P&L.
- Table: `fact_trade` (date, symbol, side, quantity, price, pnl, reason) with a sector slicer.
- Cards: Closed Trades, Win Rate %, Trading Costs.

**Page 5: Rule strategies**
- Clustered bar from `fact_strategy_backtest`: strategy by average `total_return_pct` vs `buy_hold_return_pct`.

## 5. For the portfolio

- Export screenshots of each page into `powerbi/screenshots/` and link them from the README.
- Save the file as `powerbi/Algotrader.pbix`.
- When real NSE data is added, rerun `python main.py report`, then **Home → Refresh** in Power BI.
  The schema stays the same; `dim_run[data_source]` will show `nse`.
