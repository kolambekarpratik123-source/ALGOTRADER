"""Generate a Power BI Project (.pbip) for the Algotrader dashboard.

Open powerbi/Algotrader/Algotrader.pbip in Power BI Desktop. The semantic model is written in
TMDL (plain-text model files) and loads the CSVs from `python main.py report`.

Regenerate with:  python main.py powerbi --data-folder "D:\\Algotrader\\data\\exports"
"""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from src.reporting.database import ROOT

PROJECT_DIR = ROOT / "powerbi" / "Algotrader"
NAME = "Algotrader"
NS = uuid.UUID("6a1c3f0e-2d4b-4e8a-9c7f-1b2a3c4d5e6f")


def _tag(*parts: str) -> str:
    """Stable lineage tag so regenerating doesn't look like a brand-new model."""
    return str(uuid.uuid5(NS, "/".join(parts)))


def _q(name: str) -> str:
    """Quote a TMDL object name when it has spaces or symbols."""
    return name if name.replace("_", "").isalnum() else "'" + name.replace("'", "''") + "'"


# ----------------------------------------------------------------------------- model definition
# (column, TMDL dataType, Power Query type, formatString or None)
I, F, S, D = ("int64", "Int64.Type"), ("double", "type number"), ("string", "type text"), ("dateTime", "type date")

TABLES: dict[str, list[tuple[str, tuple[str, str], str | None]]] = {
    "dim_run": [
        ("run_id", I, "0"), ("created_at", S, None), ("data_source", S, None), ("market_type", S, None),
        ("seed", I, "0"), ("signal_strength", F, "0.0"), ("is_showcase", I, "0"), ("top_k", I, "0"),
        ("rebalance_days", I, "0"), ("horizon_days", I, "0"), ("initial_capital", F, "#,0"),
        ("ic", F, "0.000"), ("ic_tstat", F, "0.00"), ("total_return_pct", F, "0.0"),
        ("benchmark_return_pct", F, "0.0"), ("cagr_pct", F, "0.0"), ("max_drawdown_pct", F, "0.0"),
        ("sharpe", F, "0.00"), ("worst_month_pct", F, "0.0"), ("total_costs", F, "#,0"),
        ("trade_count", I, "#,0"),
    ],
    "dim_date": [
        ("date", D, "yyyy-mm-dd"), ("year", I, "0"), ("quarter", I, "0"), ("month", I, "0"),
        ("month_name", S, None), ("year_month", S, None), ("week_of_year", I, "0"), ("weekday_name", S, None),
    ],
    "dim_stock": [("symbol", S, None), ("company_name", S, None), ("sector", S, None), ("data_source", S, None)],
    "fact_portfolio_daily": [
        ("run_id", I, "0"), ("date", D, "yyyy-mm-dd"), ("equity", F, "#,0"), ("benchmark_equity", F, "#,0"),
    ],
    "fact_trade": [
        ("trade_id", I, "0"), ("run_id", I, "0"), ("date", D, "yyyy-mm-dd"), ("symbol", S, None),
        ("side", S, None), ("quantity", I, "#,0"), ("price", F, "#,0.00"), ("value", F, "#,0"),
        ("charges", F, "#,0.00"), ("pnl", F, "#,0"), ("reason", S, None),
    ],
    "fact_prediction": [
        ("run_id", I, "0"), ("date", D, "yyyy-mm-dd"), ("symbol", S, None), ("score", F, "0.0000"),
        ("rank_in_day", I, "0"), ("fwd_return", F, "0.00%"), ("fold", I, "0"),
    ],
    "fact_strategy_backtest": [
        ("data_source", S, None), ("strategy", S, None), ("symbol", S, None), ("period_start", S, None),
        ("period_end", S, None), ("total_return_pct", F, "0.0"), ("buy_hold_return_pct", F, "0.0"),
        ("trade_count", I, "0"), ("win_rate_pct", F, "0.0"), ("max_drawdown_pct", F, "0.0"),
        ("sharpe", F, "0.00"), ("total_costs", F, "#,0"),
    ],
}

RELATIONSHIPS = [
    ("fact_portfolio_daily", "date", "dim_date", "date"),
    ("fact_trade", "date", "dim_date", "date"),
    ("fact_prediction", "date", "dim_date", "date"),
    ("fact_trade", "symbol", "dim_stock", "symbol"),
    ("fact_prediction", "symbol", "dim_stock", "symbol"),
    ("fact_portfolio_daily", "run_id", "dim_run", "run_id"),
    ("fact_trade", "run_id", "dim_run", "run_id"),
    ("fact_prediction", "run_id", "dim_run", "run_id"),
]

PCT = "0.0%"
RS = "#,0"
# table -> [(measure name, DAX, format, description)]
MEASURES: dict[str, list[tuple[str, str, str, str]]] = {
    "dim_run": [
        ("Total Return %", "AVERAGE ( dim_run[total_return_pct] ) / 100", PCT,
         "Ranker return over the test period, after costs"),
        ("Benchmark Return %", "AVERAGE ( dim_run[benchmark_return_pct] ) / 100", PCT,
         "Return from holding every stock equally"),
        ("Excess Return %", "[Total Return %] - [Benchmark Return %]", PCT, "Ranker minus benchmark"),
        ("Max Drawdown %", "-MAX ( dim_run[max_drawdown_pct] ) / 100", PCT, "Largest fall from a peak"),
        ("Worst Month %", "MIN ( dim_run[worst_month_pct] ) / 100", PCT, "Worst calendar month"),
        ("Avg IC", "AVERAGE ( dim_run[ic] )", "0.000",
         "Prediction accuracy: rank correlation of score vs actual return. 0 = no skill"),
        ("Runs Beating Benchmark",
         "COUNTROWS ( FILTER ( dim_run, dim_run[total_return_pct] > dim_run[benchmark_return_pct] ) )",
         "0", "Number of runs where the ranker beat holding everything"),
        ("Starting Capital", "MAX ( dim_run[initial_capital] )", RS, ""),
    ],
    "fact_portfolio_daily": [
        ("Portfolio Value", "SUM ( fact_portfolio_daily[equity] )", RS, "Portfolio value"),
        ("Benchmark Value", "SUM ( fact_portfolio_daily[benchmark_equity] )", RS, "Hold-everything value"),
        ("Drawdown %",
         "VAR d = MAX ( dim_date[date] )\n"
         "VAR eq = [Portfolio Value]\n"
         "VAR peak =\n"
         "    CALCULATE (\n"
         "        MAXX ( VALUES ( fact_portfolio_daily[date] ), CALCULATE ( SUM ( fact_portfolio_daily[equity] ) ) ),\n"
         "        REMOVEFILTERS ( dim_date ),\n"
         "        fact_portfolio_daily[date] <= d\n"
         "    )\n"
         "RETURN IF ( ISBLANK ( eq ), BLANK (), DIVIDE ( eq, peak ) - 1 )",
         PCT, "How far below its previous peak the portfolio is"),
        ("Monthly Return %",
         "VAR MonthStart = MIN ( dim_date[date] )\n"
         "VAR EndDate = CALCULATE ( MAX ( fact_portfolio_daily[date] ) )\n"
         "VAR EndVal =\n"
         "    CALCULATE ( SUM ( fact_portfolio_daily[equity] ), REMOVEFILTERS ( dim_date ), fact_portfolio_daily[date] = EndDate )\n"
         "VAR PrevDate =\n"
         "    CALCULATE ( MAX ( fact_portfolio_daily[date] ), REMOVEFILTERS ( dim_date ), fact_portfolio_daily[date] < MonthStart )\n"
         "VAR PrevVal =\n"
         "    IF (\n"
         "        ISBLANK ( PrevDate ),\n"
         "        [Starting Capital],\n"
         "        CALCULATE ( SUM ( fact_portfolio_daily[equity] ), REMOVEFILTERS ( dim_date ), fact_portfolio_daily[date] = PrevDate )\n"
         "    )\n"
         "RETURN IF ( ISBLANK ( EndDate ), BLANK (), DIVIDE ( EndVal, PrevVal ) - 1 )",
         "0.00%", "Return for the month (or any date range) in the current filter"),
    ],
    "fact_trade": [
        ("Realised P&L", "CALCULATE ( SUM ( fact_trade[pnl] ), fact_trade[side] = \"SELL\" )", RS,
         "Profit from closed trades, after all charges"),
        ("Trading Costs", "SUM ( fact_trade[charges] )", RS, "Brokerage, taxes and fees paid"),
        ("Closed Trades", "CALCULATE ( COUNTROWS ( fact_trade ), fact_trade[side] = \"SELL\" )", "#,0", ""),
        ("Win Rate %",
         "DIVIDE (\n"
         "    CALCULATE ( COUNTROWS ( fact_trade ), fact_trade[side] = \"SELL\", fact_trade[pnl] > 0 ),\n"
         "    [Closed Trades]\n"
         ")", PCT, "Share of closed trades that made money"),
    ],
    "fact_prediction": [
        ("Top Pick Return %",
         "VAR k = MAX ( dim_run[top_k] )\n"
         "RETURN CALCULATE ( AVERAGE ( fact_prediction[fwd_return] ), fact_prediction[rank_in_day] <= k )",
         "0.00%", "Average actual return of the stocks the model ranked in its top K"),
        ("Avg Stock Return %", "AVERAGE ( fact_prediction[fwd_return] )", "0.00%",
         "Average actual return of all stocks"),
        ("Pick Edge %", "[Top Pick Return %] - [Avg Stock Return %]", "0.00%",
         "How much better the top picks did than the average stock"),
    ],
    "fact_strategy_backtest": [
        ("Avg Strategy Return %", "AVERAGE ( fact_strategy_backtest[total_return_pct] ) / 100", PCT, ""),
        ("Avg Buy-Hold Return %", "AVERAGE ( fact_strategy_backtest[buy_hold_return_pct] ) / 100", PCT, ""),
        ("Avg Win Rate %", "AVERAGE ( fact_strategy_backtest[win_rate_pct] ) / 100", PCT, ""),
    ],
}


def _table_tmdl(table: str) -> str:
    cols = TABLES[table]
    lines = [f"table {table}", f"\tlineageTag: {_tag('t', table)}"]
    if table == "dim_date":
        lines.append("\tdataCategory: Time")
    lines.append("")

    for name, desc_dax, fmt, desc in MEASURES.get(table, []):
        if desc:
            lines.append(f"\t/// {desc}")
        lines.append(f"\tmeasure {_q(name)} =")
        for dax_line in desc_dax.split("\n"):
            lines.append("\t\t\t" + dax_line)
        lines.append(f"\t\tformatString: {fmt}")
        lines.append(f"\t\tlineageTag: {_tag('m', table, name)}")
        lines.append("")

    for col, (dtype, _), fmt in cols:
        lines.append(f"\tcolumn {_q(col)}")
        lines.append(f"\t\tdataType: {dtype}")
        if fmt:
            lines.append(f"\t\tformatString: {fmt}")
        if table == "dim_date" and col == "date":
            lines.append("\t\tisKey")
        lines.append(f"\t\tlineageTag: {_tag('c', table, col)}")
        lines.append("\t\tsummarizeBy: none")
        lines.append(f"\t\tsourceColumn: {col}")
        if table == "dim_date" and col == "month_name":
            lines.append("\t\tsortByColumn: month")
        lines.append("")
        lines.append("\t\tannotation SummarizationSetBy = User")
        lines.append("")

    types = ", ".join(f'{{"{c}", {pq}}}' for c, (_, pq), _ in cols)
    m = [
        "let",
        f'    Source = Csv.Document(File.Contents(DataFolder & "{table}.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
        "    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),",
        f'    Typed = Table.TransformColumnTypes(Promoted, {{{types}}}, "en-US")',
        "in",
        "    Typed",
    ]
    lines.append(f"\tpartition {table} = m")
    lines.append("\t\tmode: import")
    lines.append("\t\tsource =")
    lines.extend("\t\t\t\t" + x for x in m)
    lines.append("")
    lines.append("\tannotation PBI_ResultType = Table")
    lines.append("")
    return "\n".join(lines)


def _semantic_model(root: Path, data_folder: str) -> None:
    sm = root / f"{NAME}.SemanticModel"
    d = sm / "definition"
    (d / "tables").mkdir(parents=True, exist_ok=True)
    (sm / "definition.pbism").write_text(json.dumps({"version": "4.0", "settings": {}}, indent=2))
    (sm / ".platform").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "SemanticModel", "displayName": NAME},
        "config": {"version": "2.0", "logicalId": _tag("logical", "model")},
    }, indent=2))
    (d / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1567\n")
    model = ["model Model", "\tculture: en-US", "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
             "\tsourceQueryCulture: en-US", "\tdataAccessOptions", "\t\tlegacyRedirects",
             "\t\treturnErrorValuesAsNull", "",
             "annotation PBI_QueryOrder = " + json.dumps(["DataFolder", *TABLES]), ""]
    model += [f"ref table {t}" for t in TABLES]
    (d / "model.tmdl").write_text("\n".join(model) + "\n")
    folder = data_folder.rstrip("\\/") + "\\"
    (d / "expressions.tmdl").write_text(
        f'expression DataFolder = "{folder}" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]\n'
        f"\tlineageTag: {_tag('expr', 'DataFolder')}\n\n"
        "\tannotation PBI_ResultType = Text\n"
    )
    rels = []
    for ft, fc, tt, tc in RELATIONSHIPS:
        rels += [f"relationship {_tag('r', ft, fc, tt)}", f"\tfromColumn: {ft}.{_q(fc)}",
                 f"\ttoColumn: {tt}.{_q(tc)}", ""]
    (d / "relationships.tmdl").write_text("\n".join(rels))
    for t in TABLES:
        (d / "tables" / f"{t}.tmdl").write_text(_table_tmdl(t))


# ----------------------------------------------------------------------------- report definition
# Written in PBIR (the report format Power BI Desktop has saved by default since 2025): one folder per
# page and one visual.json per visual. Schema versions match what Power BI Desktop 2.159 (Oct 2026) writes.
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"
SCHEMAS = {
    "report": f"{SCHEMA}/report/3.3.0/schema.json",
    "version": f"{SCHEMA}/versionMetadata/1.0.0/schema.json",
    "pages": f"{SCHEMA}/pagesMetadata/1.1.0/schema.json",
    "page": f"{SCHEMA}/page/2.1.0/schema.json",
    "visual": f"{SCHEMA}/visualContainer/2.14.0/schema.json",
}
BASE_THEME = "Fluent2-CY26SU10"
REPORT_VERSION_AT_IMPORT = {"visual": "2.14.0", "report": "3.4.0", "page": "2.3.1"}
THEME_DIR = ROOT / "powerbi" / "base_theme"
PAGE_W, PAGE_H = 1280, 720


def _measure_table(name: str) -> str:
    for table, ms in MEASURES.items():
        if any(m[0] == name for m in ms):
            return table
    raise KeyError(name)


def _lit(v: str) -> dict:
    return {"expr": {"Literal": {"Value": v}}}


def _field_ref(f: str) -> tuple[dict, str, str]:
    """'#Measure Name' or 'table.column' -> (field expression, queryRef, nativeQueryRef)."""
    if f.startswith("#"):
        prop = f[1:]
        entity = _measure_table(prop)
        field = {"Measure": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}
    else:
        entity, prop = f.split(".", 1)
        field = {"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}
    return field, f"{entity}.{prop}", prop


def _visual(vid: str, vtype: str, x: int, y: int, w: int, h: int, roles: dict[str, list[str]],
            title: str | None = None, z: int = 0) -> dict:
    """roles: {"Category": ["dim_date.date"], "Y": ["#Portfolio Value"]}. '#Name' = measure, 'table.col' = column."""
    query_state = {}
    for role, fields in roles.items():
        projections = []
        for f in fields:
            field, qref, native = _field_ref(f)
            proj = {"field": field, "queryRef": qref, "nativeQueryRef": native}
            if role in ("Category", "Rows", "Columns") and not f.startswith("#"):
                proj["active"] = True
            projections.append(proj)
        query_state[role] = {"projections": projections}
    visual: dict = {"visualType": vtype, "query": {"queryState": query_state}, "drillFilterOtherVisuals": True}
    if title:
        visual["visualContainerObjects"] = {"title": [{"properties": {
            "show": _lit("true"),
            "text": _lit("'" + title.replace("'", "''") + "'"),
        }}]}
    return {
        "$schema": SCHEMAS["visual"],
        "name": vid,
        "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z},
        "visual": visual,
    }


def _textbox(vid: str, text: str, x: int, y: int, w: int, h: int, size: str = "11pt", bold: bool = False,
             color: str = "#252423") -> dict:
    style = {"fontSize": size, "color": color}
    if bold:
        style["fontWeight"] = "bold"
    return {
        "$schema": SCHEMAS["visual"],
        "name": vid,
        "position": {"x": x, "y": y, "z": 0, "height": h, "width": w, "tabOrder": 0},
        "visual": {"visualType": "textbox", "objects": {"general": [{"properties": {
            "paragraphs": [{"textRuns": [{"value": text, "textStyle": style}]}]}}]},
            "drillFilterOtherVisuals": True},
    }


def _showcase_filter() -> dict:
    col = {"Column": {"Expression": {"SourceRef": {"Entity": "dim_run"}}, "Property": "is_showcase"}}
    return {"filters": [{
        "name": "ShowcaseRunOnly",
        "field": col,
        "type": "Categorical",
        "filter": {"Version": 2, "From": [{"Name": "d", "Entity": "dim_run", "Type": 0}], "Where": [{
            "Condition": {"In": {
                "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "d"}}, "Property": "is_showcase"}}],
                "Values": [[{"Literal": {"Value": "1L"}}]],
            }}}]},
        "howCreated": "User",
    }]}


def _header(page: str, subtitle: str) -> list[dict]:
    return [
        _textbox(f"{page}_title", subtitle, 20, 10, 900, 40, "20pt", True, "#1F3864"),
        _textbox(f"{page}_note", "Synthetic market data: shows the method, not real-world profit.",
                 20, 48, 900, 26, "10pt", False, "#7F7F7F"),
    ]


def _pages() -> list[tuple[str, str, list[dict], dict | None]]:
    """(page id, display name, visuals, page filterConfig or None)."""
    pages = []

    # 1. Overview (showcase run)
    cards = ["Total Return %", "Benchmark Return %", "Excess Return %", "Max Drawdown %", "Avg IC", "Trading Costs"]
    v = _header("ov", "AI Stock Ranker: Overview")
    for i, m in enumerate(cards):
        v.append(_visual(f"ov_card{i}", "card", 20 + i * 207, 85, 197, 110, {"Values": [f"#{m}"]}, z=10 + i))
    v.append(_visual("ov_equity", "lineChart", 20, 210, 1240, 490,
                     {"Category": ["dim_date.date"], "Y": ["#Portfolio Value", "#Benchmark Value"]},
                     "Portfolio value: ranker vs. holding every stock (Rs)", z=20))
    pages.append(("overview", "Overview", v, _showcase_filter()))

    # 2. Monthly performance (showcase run)
    v = _header("mo", "Monthly performance")
    v.append(_visual("mo_matrix", "pivotTable", 20, 85, 1240, 300,
                     {"Rows": ["dim_date.year"], "Columns": ["dim_date.month_name"], "Values": ["#Monthly Return %"]},
                     "Monthly return (%)", z=10))
    v.append(_visual("mo_dd", "areaChart", 20, 400, 1240, 300,
                     {"Category": ["dim_date.date"], "Y": ["#Drawdown %"]}, "Drawdown from previous peak", z=11))
    pages.append(("monthly", "Monthly", v, _showcase_filter()))

    # 3. Does the model work? (all runs)
    v = _header("mw", "Does the model work? Pattern markets vs. pure noise")
    v.append(_visual("mw_ic", "clusteredColumnChart", 20, 85, 400, 300,
                     {"Category": ["dim_run.market_type"], "Y": ["#Avg IC"]},
                     "Prediction accuracy (IC). Noise should be ~0", z=10))
    v.append(_visual("mw_ret", "clusteredColumnChart", 440, 85, 400, 300,
                     {"Category": ["dim_run.market_type"], "Y": ["#Total Return %", "#Benchmark Return %"]},
                     "Average return vs. holding everything", z=11))
    v.append(_visual("mw_scatter", "scatterChart", 860, 85, 400, 300,
                     {"Category": ["dim_run.run_id"], "Series": ["dim_run.market_type"],
                      "X": ["#Avg IC"], "Y": ["#Total Return %"]},
                     "Each run: accuracy vs. return", z=12))
    v.append(_visual("mw_edge_card", "card", 20, 400, 300, 120, {"Values": ["#Pick Edge %"]}, z=13))
    v.append(_visual("mw_edge", "lineChart", 340, 400, 920, 300,
                     {"Category": ["dim_date.year_month"], "Y": ["#Pick Edge %"]},
                     "Top picks minus average stock, by month (showcase run)", z=14))
    pages.append(("modelcheck", "Model check", v, None))

    # 4. Trades & sectors (showcase run)
    v = _header("tr", "Trades and sectors")
    for i, m in enumerate(["Closed Trades", "Win Rate %", "Realised P&L", "Trading Costs"]):
        v.append(_visual(f"tr_card{i}", "card", 20 + i * 160, 85, 150, 100, {"Values": [f"#{m}"]}, z=10 + i))
    v.append(_visual("tr_sector", "clusteredBarChart", 20, 200, 620, 500,
                     {"Category": ["dim_stock.sector"], "Y": ["#Realised P&L"]}, "Realised P&L by sector (Rs)", z=20))
    v.append(_visual("tr_table", "tableEx", 660, 85, 600, 615,
                     {"Values": ["fact_trade.trade_id", "fact_trade.date", "fact_trade.symbol", "fact_trade.side",
                                 "fact_trade.quantity", "fact_trade.price", "fact_trade.pnl", "fact_trade.reason"]},
                     "Trade log", z=21))
    pages.append(("trades", "Trades", v, _showcase_filter()))

    # 5. Rule strategies
    v = _header("rs", "Old rule-based strategies vs. buy-and-hold")
    v.append(_visual("rs_bar", "clusteredBarChart", 20, 85, 820, 615,
                     {"Category": ["fact_strategy_backtest.strategy"],
                      "Y": ["#Avg Strategy Return %", "#Avg Buy-Hold Return %"]},
                     "Average return per strategy vs. buy-and-hold", z=10))
    v.append(_visual("rs_win", "clusteredColumnChart", 860, 85, 400, 615,
                     {"Category": ["fact_strategy_backtest.strategy"], "Y": ["#Avg Win Rate %"]}, "Win rate", z=11))
    pages.append(("rulestrategies", "Rule strategies", v, None))
    return pages


def _find_base_theme() -> Path | None:
    """Power BI needs its base theme file next to the report. It ships with Power BI Desktop, so we
    copy it from powerbi/base_theme/ (saved there from any report Desktop has written)."""
    exact = THEME_DIR / f"{BASE_THEME}.json"
    if exact.exists():
        return exact
    found = sorted(THEME_DIR.glob("*.json")) if THEME_DIR.exists() else []
    return found[-1] if found else None


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _report(root: Path) -> None:
    rp = root / f"{NAME}.Report"
    d = rp / "definition"
    _write_json(rp / "definition.pbir",
                {"version": "4.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}})
    _write_json(rp / ".platform", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "Report", "displayName": NAME},
        "config": {"version": "2.0", "logicalId": _tag("logical", "report")},
    })
    _write_json(d / "version.json", {"$schema": SCHEMAS["version"], "version": "2.0.0"})

    theme = _find_base_theme()
    theme_name = theme.stem if theme else BASE_THEME
    if theme:
        dest = rp / "StaticResources" / "SharedResources" / "BaseThemes" / f"{theme_name}.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(theme, dest)
    report = {
        "$schema": SCHEMAS["report"],
        "themeCollection": {"baseTheme": {
            "name": theme_name, "reportVersionAtImport": REPORT_VERSION_AT_IMPORT, "type": "SharedResources"}},
        "objects": {"section": [{"properties": {"verticalAlignment": _lit("'Top'")}}]},
        "resourcePackages": [{"name": "SharedResources", "type": "SharedResources", "items": [
            {"name": theme_name, "path": f"BaseThemes/{theme_name}.json", "type": "BaseTheme"}]}],
        "settings": {
            "useStylableVisualContainerHeader": True,
            "exportDataMode": "AllowSummarized",
            "defaultDrillFilterOtherVisuals": True,
            "allowChangeFilterTypes": True,
            "useEnhancedTooltips": True,
            "useDefaultAggregateDisplayName": True,
        },
    }
    _write_json(d / "report.json", report)

    pages = _pages()
    _write_json(d / "pages" / "pages.json", {
        "$schema": SCHEMAS["pages"], "pageOrder": [p[0] for p in pages], "activePageName": pages[0][0]})
    for pid, display, visuals, filters in pages:
        page = {"$schema": SCHEMAS["page"], "name": pid, "displayName": display,
                "displayOption": "FitToPage", "height": PAGE_H, "width": PAGE_W}
        if filters:
            page["filterConfig"] = filters
        _write_json(d / "pages" / pid / "page.json", page)
        for vis in visuals:
            _write_json(d / "pages" / pid / "visuals" / vis["name"] / "visual.json", vis)


def build_powerbi_project(data_folder: str = r"D:\Algotrader\data\exports", out_dir: Path = PROJECT_DIR) -> Path:
    """Write the .pbip project. Returns the .pbip path.

    If powerbi/base_theme/ has no theme file yet, the report is still written but Power BI may refuse
    to draw visuals: copy StaticResources/SharedResources/BaseThemes/*.json from any report your
    Power BI Desktop has saved as .pbip into powerbi/base_theme/ and run this again.
    """
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    _semantic_model(out_dir, data_folder)
    _report(out_dir)
    (out_dir / f"{NAME}.pbip").write_text(json.dumps({
        "version": "1.0",
        "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
        "settings": {"enableAutoRecovery": True},
    }, indent=2))
    (out_dir / ".gitignore").write_text("**/.pbi/localSettings.json\n**/.pbi/cache.abf\n")
    return out_dir / f"{NAME}.pbip"
