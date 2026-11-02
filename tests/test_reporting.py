"""Reporting tests: database loads, every SQL query runs, Excel builds."""

from pathlib import Path

import pytest
from openpyxl import load_workbook

from src.ml.pipeline import RankerConfig, run_ranker
from src.reporting import database as db
from src.reporting.excel import build_excel


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("rep")
    runs: list = []
    run_ranker(RankerConfig(n_stocks=30, years=4, seeds=(1,), signal_strength=2.0), collect=runs, output_file=None)
    path = db.build_database(runs, db_path=tmp / "t.db")
    return tmp, path, runs


def test_tables_have_rows(built):
    _, path, runs = built
    conn = db.connect(path)
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ["dim_run", "dim_date", "dim_stock", "fact_price", "fact_prediction",
                        "fact_trade", "fact_portfolio_daily"]}
    conn.close()
    assert counts["dim_run"] == len(runs) == 2          # one pattern + one noise run
    assert all(v > 0 for v in counts.values()), counts


def test_trade_pnl_matches_portfolio(built):
    """Realised P&L in SQL must equal the simulator's final gain (everything is closed at the end)."""
    _, path, runs = built
    conn = db.connect(path)
    pnl, ret, cap = conn.execute(
        "SELECT SUM(t.pnl), r.total_return_pct, r.initial_capital FROM fact_trade t "
        "JOIN dim_run r ON r.run_id = t.run_id WHERE r.run_id = 1 AND t.side = 'SELL'").fetchone()
    conn.close()
    assert pnl == pytest.approx(cap * ret / 100, abs=50)


def test_every_analysis_query_runs(built):
    _, path, _ = built
    results = db.run_analysis_queries(path)
    assert len(results) == len(list(db.ANALYSIS_DIR.glob("*.sql")))
    assert len(results["04_model_accuracy_by_decile"]) == 10


def test_excel_and_csv(built):
    tmp, path, _ = built
    xl = build_excel(path, tmp / "r.xlsx")
    assert {"Summary", "Monthly Returns", "Trades"} <= set(load_workbook(xl).sheetnames)
    csvs = db.export_csv(path, tmp / "csv")
    assert any(p.name == "fact_trade.csv" for p in csvs)


def test_powerbi_project_is_consistent(tmp_path):
    """Every field a visual uses must exist in the model (PBIR format: one visual.json per visual)."""
    import json

    from src.reporting.powerbi import MEASURES, TABLES, build_powerbi_project

    pbip = build_powerbi_project(r"C:\x\exports", tmp_path / "pbi")
    defn = pbip.parent / "Algotrader.Report" / "definition"
    cols = {(t, c) for t, cs in TABLES.items() for c, _, _ in cs}
    meas = {(t, m[0]) for t, ms in MEASURES.items() for m in ms}
    pages = json.loads((defn / "pages" / "pages.json").read_text())["pageOrder"]
    assert len(pages) == 5
    n = 0
    for vf in defn.glob("pages/*/visuals/*/visual.json"):
        vis = json.loads(vf.read_text())["visual"]
        for role in vis.get("query", {}).get("queryState", {}).values():
            for proj in role["projections"]:
                kind = "Measure" if "Measure" in proj["field"] else "Column"
                f = proj["field"][kind]
                key = (f["Expression"]["SourceRef"]["Entity"], f["Property"])
                assert key in (meas if kind == "Measure" else cols), key
                n += 1
    assert n > 30
    assert len(list((pbip.parent / "Algotrader.SemanticModel" / "definition" / "tables").glob("*.tmdl"))) == len(TABLES)


def test_powerbi_measure_names_do_not_clash_with_columns():
    """Power BI names are case-insensitive: a measure can't share a name with any column."""
    from src.reporting.powerbi import MEASURES, TABLES

    cols = {c.lower() for cs in TABLES.values() for c, _, _ in cs}
    measures = [m[0].lower() for ms in MEASURES.values() for m in ms]
    assert len(measures) == len(set(measures))
    assert not (set(measures) & cols)
