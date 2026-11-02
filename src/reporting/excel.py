"""Build the Excel report from the SQLite database. Every sheet is fed by a query in sql/analysis/."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from src.reporting.database import DB_PATH, ROOT, connect, run_analysis_queries

EXCEL_PATH = ROOT / "data" / "Algotrader_Report.xlsx"
HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=16, color="1F3864")
NOTE_FONT = Font(italic=True, size=9, color="7F7F7F")


def _write_table(ws, df: pd.DataFrame, top: int, left: int = 1, name: str | None = None,
                 number_formats: dict[str, str] | None = None) -> tuple[int, int]:
    """Write a DataFrame as a formatted Excel table. Returns (last_row, last_col)."""
    for j, col in enumerate(df.columns):
        c = ws.cell(row=top, column=left + j, value=str(col).replace("_", " ").title())
        c.fill, c.font = HEADER_FILL, HEADER_FONT
        c.alignment = Alignment(horizontal="center", wrap_text=True)
    for i, row in enumerate(df.itertuples(index=False), start=1):
        for j, v in enumerate(row):
            v = None if (isinstance(v, float) and pd.isna(v)) else v
            cell = ws.cell(row=top + i, column=left + j, value=v)
            fmt = (number_formats or {}).get(df.columns[j])
            if fmt:
                cell.number_format = fmt
    last_row, last_col = top + len(df), left + len(df.columns) - 1
    if name and len(df):
        ref = f"{get_column_letter(left)}{top}:{get_column_letter(last_col)}{last_row}"
        t = Table(displayName=name, ref=ref)
        t.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
        ws.add_table(t)
    for j, col in enumerate(df.columns):
        width = max(len(str(col)), *(len(str(x)) for x in df[col].head(200))) if len(df) else len(str(col))
        ws.column_dimensions[get_column_letter(left + j)].width = min(max(10, width + 2), 40)
    return last_row, last_col


def _title(ws, text: str, note: str) -> None:
    ws["A1"] = text
    ws["A1"].font = TITLE_FONT
    ws["A2"] = note
    ws["A2"].font = NOTE_FONT


def build_excel(db_path: Path = DB_PATH, out_path: Path = EXCEL_PATH) -> Path:
    q = run_analysis_queries(db_path)
    conn = connect(db_path)
    try:
        run = pd.read_sql_query("SELECT * FROM dim_run WHERE is_showcase = 1", conn).iloc[0]
        curve = pd.read_sql_query(
            "SELECT p.date, p.equity, p.benchmark_equity FROM fact_portfolio_daily p "
            "JOIN dim_run r ON r.run_id = p.run_id WHERE r.is_showcase = 1 ORDER BY p.date", conn)
        trades = pd.read_sql_query(
            "SELECT t.trade_id, t.date, t.symbol, s.sector, t.side, t.quantity, t.price, t.value, "
            "t.charges, t.pnl, t.reason FROM fact_trade t JOIN dim_stock s ON s.symbol = t.symbol "
            "JOIN dim_run r ON r.run_id = t.run_id WHERE r.is_showcase = 1 ORDER BY t.trade_id", conn)
    finally:
        conn.close()

    wb = Workbook()
    synthetic_note = ("Synthetic market data: this demonstrates the method, not real-world profit. "
                      f"Data source: {run.data_source}.")

    # 1. Summary
    ws = wb.active
    ws.title = "Summary"
    _title(ws, "Algotrader: AI Stock Ranker Report", synthetic_note)
    kpis = pd.DataFrame([
        ("Starting capital (Rs)", run.initial_capital, "#,##0"),
        ("Ranker total return", run.total_return_pct / 100, "0.0%"),
        ("Hold-everything return", run.benchmark_return_pct / 100, "0.0%"),
        ("Ranker CAGR", run.cagr_pct / 100, "0.0%"),
        ("Max drawdown", -run.max_drawdown_pct / 100, "0.0%"),
        ("Worst month", run.worst_month_pct / 100, "0.0%"),
        ("Sharpe ratio", run.sharpe, "0.00"),
        ("Prediction accuracy (IC)", run.ic, "0.000"),
        ("Trades", run.trade_count, "#,##0"),
        ("Trading costs paid (Rs)", run.total_costs, "#,##0"),
    ], columns=["metric", "value", "fmt"])
    ws["A4"] = "Showcase run"
    ws["A4"].font = Font(bold=True, size=12)
    for i, (m, v, fmt) in enumerate(kpis.itertuples(index=False), start=5):
        ws.cell(row=i, column=1, value=m).font = Font(bold=True)
        c = ws.cell(row=i, column=2, value=float(v))
        c.number_format = fmt
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 16
    ws["D4"] = "All runs: pattern vs. pure noise (sql/analysis/01_ranker_vs_benchmark.sql)"
    ws["D4"].font = Font(bold=True, size=12)
    _write_table(ws, q["01_ranker_vs_benchmark"], top=5, left=4, name="RunsSummary")
    ws["D10"] = ("How to read this: on 'noise' markets there is nothing to predict, so IC should be ~0. "
                 "Any return above the benchmark there is luck.")
    ws["D10"].font = NOTE_FONT

    # 2. Monthly returns heatmap
    ws = wb.create_sheet("Monthly Returns")
    _title(ws, "Monthly returns: ranker (%)", "Source: sql/analysis/02_monthly_returns.sql. Green = gain, red = loss.")
    m = q["02_monthly_returns"].copy()
    m["year"] = m["year_month"].str[:4]
    m["month"] = pd.to_datetime(m["year_month"]).dt.strftime("%b")
    order = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    pivot = m.pivot(index="year", columns="month", values="ranker_return_pct").reindex(columns=order)
    pivot["Full Year"] = m.groupby("year")["ranker_return_pct"].apply(lambda r: ((1 + r / 100).prod() - 1) * 100)
    pivot = pivot.round(2).reset_index()
    last_row, last_col = _write_table(ws, pivot, top=4)
    rng = f"B5:{get_column_letter(last_col - 1)}{last_row}"
    ws.conditional_formatting.add(rng, ColorScaleRule(
        start_type="num", start_value=-8, start_color="F8696B",
        mid_type="num", mid_value=0, mid_color="FFFFFF",
        end_type="num", end_value=8, end_color="63BE7B"))
    _write_table(ws, q["02_monthly_returns"], top=last_row + 3, name="MonthlyReturns")

    # 3. Equity curve
    ws = wb.create_sheet("Equity Curve")
    _title(ws, "Portfolio value: ranker vs. hold everything", "Daily values for the showcase run (Rs).")
    weekly = curve.iloc[::5].reset_index(drop=True)
    last_row, _ = _write_table(ws, weekly, top=4, name="EquityCurve",
                               number_formats={"equity": "#,##0", "benchmark_equity": "#,##0"})
    ch = LineChart()
    ch.title, ch.y_axis.title, ch.height, ch.width = "Portfolio value (Rs)", "Rs", 10, 24
    ch.add_data(Reference(ws, min_col=2, max_col=3, min_row=4, max_row=last_row), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=1, min_row=5, max_row=last_row))
    ch.x_axis.number_format, ch.x_axis.tickLblSkip = "yyyy-mm", 26
    ws.add_chart(ch, "E4")

    # 4. Model accuracy
    ws = wb.create_sheet("Model Accuracy")
    _title(ws, "Does a higher score mean a higher return?",
           "Source: sql/analysis/04_model_accuracy_by_decile.sql. Decile 10 = stocks the model liked most.")
    last_row, _ = _write_table(ws, q["04_model_accuracy_by_decile"], top=4, name="Deciles")
    ch = BarChart()
    ch.title, ch.y_axis.title, ch.x_axis.title, ch.height, ch.width = (
        "Average actual return by model decile (%)", "%", "Decile", 9, 18)
    ch.add_data(Reference(ws, min_col=3, min_row=4, max_row=last_row), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=1, min_row=5, max_row=last_row))
    ws.add_chart(ch, "G4")
    _write_table(ws, q["07_pick_hit_rate_by_quarter"], top=last_row + 3, name="HitRate")

    # 5. Sectors and stocks
    ws = wb.create_sheet("Sectors & Stocks")
    _title(ws, "Where the profit came from", "Sources: 05_trades_by_sector.sql, 06_top_and_bottom_stocks.sql")
    last_row, _ = _write_table(ws, q["05_trades_by_sector"], top=4, name="Sectors")
    ch = BarChart()
    ch.type, ch.title, ch.height, ch.width = "bar", "Realised P&L by sector (Rs)", 9, 18
    ch.add_data(Reference(ws, min_col=4, min_row=4, max_row=last_row), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=1, min_row=5, max_row=last_row))
    ws.add_chart(ch, "I4")
    last_row, _ = _write_table(ws, q["06_top_and_bottom_stocks"], top=last_row + 3, name="TopBottom")
    _write_table(ws, q["08_cost_drag_by_year"], top=last_row + 3, name="CostDrag")

    # 6. Trades
    ws = wb.create_sheet("Trades")
    _title(ws, "Every trade (showcase run)", "Filter with the header arrows. P&L is after all charges.")
    _write_table(ws, trades, top=4, name="Trades",
                 number_formats={"price": "#,##0.00", "value": "#,##0", "charges": "#,##0.00", "pnl": "#,##0"})
    ws.freeze_panes = "A5"

    # 7. Rule strategies
    ws = wb.create_sheet("Rule Strategies")
    _title(ws, "Old rule-based strategies vs. buy-and-hold", "Source: 09_rule_strategies_vs_buy_hold.sql")
    _write_table(ws, q["09_rule_strategies_vs_buy_hold"], top=4, name="RuleStrategies")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return out_path
