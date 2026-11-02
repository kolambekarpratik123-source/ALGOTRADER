"""CLI Entry Point for Algotrader Pro."""

import asyncio
import sys
from pathlib import Path

import click
from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rich.table import Table

from src.backtest import ZERO_COSTS, BacktestEngine, CostModel
from src.backtest.baseline import DEFAULT_SYMBOLS, run_baseline
from src.config import Settings
from src.data import create_data_provider
from src.data.historical import load_daily_candles
from src.engine import TradingEngine
from src.strategies.registry import get_strategy, list_strategies

console = Console()


@click.group()
def cli():
    """Algotrader Pro — Algorithmic Trading Platform for BSE/NSE."""
    pass


@cli.command()
@click.option("--mode", type=click.Choice(["paper", "live"]), default=None, help="Trading mode")
@click.option("--strategy", type=click.Choice(list_strategies()), default=None, help="Strategy to run")
@click.option("--interval", type=int, default=10, help="Cycle interval in seconds")
@click.option("--cycles", type=int, default=None, help="Max cycles to run (None for infinite)")
def run(mode, strategy, interval, cycles):
    """Run the live or paper trading engine."""
    settings = Settings()
    if mode:
        settings.trading_mode = mode
    if strategy:
        settings.strategy = strategy

    console.print(f"[bold green]Starting Algotrader Pro[/bold green]")
    console.print(f"Mode: [cyan]{settings.trading_mode.value}[/cyan] | Strategy: [yellow]{settings.strategy}[/yellow]")

    provider = create_data_provider(
        settings.trading_mode.value,
        settings.kite_api_key,
        settings.kite_access_token,
    )
    engine = TradingEngine(settings, provider)

    try:
        asyncio.run(engine.run(interval_seconds=interval, max_cycles=cycles))
    except KeyboardInterrupt:
        console.print("\n[bold red]Engine stopped by user.[/bold red]")


@cli.command()
@click.option("--symbol", default="RELIANCE", help="Symbol to backtest")
@click.option("--strategy", type=click.Choice(list_strategies()), default="ma_crossover", help="Strategy")
@click.option("--source", type=click.Choice(["yfinance", "synthetic", "mock"]), default="yfinance",
              help="yfinance = real daily prices, synthetic = random test data, mock = old intraday mock")
@click.option("--years", default=5, help="Years of daily history (yfinance/synthetic)")
@click.option("--candles", default=200, help="Number of candles (mock source only)")
@click.option("--exchange", type=click.Choice(["NSE", "BSE"]), default="NSE")
@click.option("--position-pct", type=float, default=100.0, help="%% of capital per trade")
@click.option("--no-costs", is_flag=True, help="Ignore brokerage, taxes and slippage")
def backtest(symbol, strategy, source, years, candles, exchange, position_pct, no_costs):
    """Backtest one strategy on one symbol, with costs, vs buy-and-hold."""
    settings = Settings(exchange=exchange, max_position_size_pct=position_pct)
    strat = get_strategy(strategy)
    costs = ZERO_COSTS if no_costs else CostModel()

    console.print(f"[bold blue]Running Backtest[/bold blue] | {symbol} | {strategy} | {source}")
    if source == "synthetic":
        console.print("[yellow]Synthetic data: checks the code runs, says nothing about real markets.[/yellow]")

    if source == "mock":
        async def _fetch():
            provider = create_data_provider("paper")
            await provider.connect()
            data = await provider.get_candles(symbol, exchange, count=candles)
            await provider.disconnect()
            return data

        c_list = asyncio.run(_fetch())
    else:
        c_list = load_daily_candles(symbol, exchange, years, source=source)

    result = BacktestEngine(settings, strat, costs).run(symbol, c_list)

    console.print(f"\n[bold]Backtest Results for {symbol}[/bold] ({result.period_start[:10]} to {result.period_end[:10]})")
    console.print(f"Return: {result.total_return_pct:+.2f}%  |  Buy-and-hold: {result.buy_hold_return_pct:+.2f}%")
    console.print(f"Trades: {result.total_trades} | Win Rate: {result.win_rate:.1f}% | Time in market: {result.exposure_pct:.0f}%")
    console.print(f"Max Drawdown: [red]{result.max_drawdown_pct:.2f}%[/red] | Sharpe: {result.sharpe_ratio:.2f}")
    console.print(f"Costs paid: Rs {result.total_costs:,.0f}")


@cli.command()
@click.option("--symbols", default=",".join(DEFAULT_SYMBOLS), help="Comma-separated symbols")
@click.option("--source", type=click.Choice(["yfinance", "synthetic"]), default="yfinance")
@click.option("--years", default=5, help="Years of daily history")
@click.option("--exchange", type=click.Choice(["NSE", "BSE"]), default="NSE")
@click.option("--position-pct", type=float, default=100.0,
              help="%% of capital per trade (100 = fair comparison with buy-and-hold)")
def baseline(symbols, source, years, exchange, position_pct):
    """Run all strategies on many symbols and compare with buy-and-hold."""
    settings = Settings(exchange=exchange, max_position_size_pct=position_pct)
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]

    if source == "synthetic":
        console.print("[yellow]Synthetic data: checks the code runs, says nothing about real markets.[/yellow]")

    report = run_baseline(
        settings, syms, source=source, years=years,
        on_progress=lambda r: console.print(
            f"  {r.symbol:<12} {r.strategy:<13} {r.total_return_pct:+8.2f}%  (hold {r.buy_hold_return_pct:+.2f}%)"
        ),
    )

    table = Table(title=f"Baseline: {len(syms)} symbols, {years}y {source} data, after costs")
    for col in ["Strategy", "Avg return", "Avg buy-hold", "Beat hold", "Avg Sharpe", "Worst DD", "Trades", "Win rate"]:
        table.add_column(col)
    for s in report["summary"]:
        table.add_row(
            s["strategy"], f"{s['avg_return_pct']:+.1f}%", f"{s['avg_buy_hold_pct']:+.1f}%",
            f"{s['beat_buy_hold']}/{s['symbols_tested']}", f"{s['avg_sharpe']:.2f}",
            f"{s['worst_drawdown_pct']:.1f}%", str(s["total_trades"]), f"{s['avg_win_rate']:.0f}%",
        )
    console.print(table)
    for sym, err in report["errors"].items():
        console.print(f"[red]Skipped {sym}: {err}[/red]")
    console.print("Saved to data/baseline_results.json")


@cli.command()
@click.option("--signal", type=float, default=1.0,
              help="Strength of the hidden pattern in the synthetic market (0 = pure noise)")
@click.option("--stocks", default=100, help="Number of synthetic stocks")
@click.option("--years", default=6, help="Years of synthetic history")
@click.option("--seeds", default=5, help="How many different random markets to test on")
@click.option("--top", default=10, help="How many top-ranked stocks to hold")
@click.option("--rebalance", default=20, help="Trading days between rebalances")
def ranker(signal, stocks, years, seeds, top, rebalance):
    """Train and test the AI stock ranker on synthetic markets (with a luck check)."""
    from src.ml.pipeline import RankerConfig, run_ranker

    cfg = RankerConfig(
        n_stocks=stocks, years=years, signal_strength=signal,
        seeds=tuple(range(1, seeds + 1)), top_k=top, rebalance_days=rebalance,
    )
    console.print("[yellow]Synthetic markets only: this checks the method, not real-world profit.[/yellow]")
    report = run_ranker(cfg, on_progress=lambda kind, r: console.print(
        f"  seed {r['seed']} {kind:<8} IC {r['ic']:+.3f}  return {r['total_return_pct']:+7.1f}%  "
        f"(hold-all {r['benchmark_return_pct']:+6.1f}%)"
    ))

    table = Table(title="AI ranker: pattern vs. pure noise (averages across seeds, after costs)")
    for col in ["Market", "Avg IC", "Avg return", "Hold-all", "Beat hold-all", "Worst DD", "Worst month", "Avg costs"]:
        table.add_column(col)
    for label, s in [("With pattern", report["pattern_summary"]), ("Pure noise", report["noise_summary"])]:
        table.add_row(
            label, f"{s['avg_ic']:+.3f}", f"{s['avg_return_pct']:+.1f}%", f"{s['avg_benchmark_pct']:+.1f}%",
            f"{s['beat_benchmark']}/{s['seeds']}", f"{s['worst_drawdown_pct']:.1f}%",
            f"{s['worst_month_pct']:.1f}%", f"Rs {s['avg_costs']:,.0f}",
        )
    console.print(table)
    colour = "green" if report["verdict"].startswith("PASS") else "red"
    console.print(f"[bold {colour}]{report['verdict']}[/bold {colour}]")
    console.print("Top picks today (synthetic): " + ", ".join(p["symbol"] for p in report["latest_picks"]))
    console.print("Saved to data/ranker_results.json")


@cli.command()
@click.option("--seeds", default=5, help="Synthetic markets per type (pattern and noise)")
@click.option("--signal", type=float, default=1.0, help="Hidden pattern strength for 'pattern' markets")
@click.option("--no-csv", is_flag=True, help="Skip the CSV exports for Power BI")
def report(seeds, signal, no_csv):
    """Run the ranker, then build the SQL database, Excel report and Power BI CSV exports."""
    from src.ml.pipeline import RankerConfig, run_ranker
    from src.reporting.database import build_database, export_csv, run_analysis_queries
    from src.reporting.excel import build_excel

    console.print("[yellow]Synthetic markets only: this checks the method, not real-world profit.[/yellow]")
    runs: list = []
    cfg = RankerConfig(signal_strength=signal, seeds=tuple(range(1, seeds + 1)))
    run_ranker(cfg, collect=runs, on_progress=lambda kind, r: console.print(
        f"  seed {r['seed']} {kind:<8} IC {r['ic']:+.3f}  return {r['total_return_pct']:+7.1f}%"))

    db = build_database(runs)
    console.print(f"[green]Database:[/green] {db}")
    results = run_analysis_queries(db)
    console.print(f"[green]SQL analysis:[/green] {len(results)} queries in sql/analysis/ ran OK")
    xl = build_excel(db)
    console.print(f"[green]Excel report:[/green] {xl}")
    if not no_csv:
        paths = export_csv(db)
        console.print(f"[green]Power BI CSVs:[/green] {len(paths)} files in {paths[0].parent}")
    from src.reporting.powerbi import build_powerbi_project

    pbip = build_powerbi_project(str(Path(__file__).resolve().parent / "data" / "exports"))
    console.print(f"[green]Power BI project:[/green] {pbip} (open it in Power BI Desktop)")


@cli.command()
@click.option("--data-folder", default=None,
              help="Full path to data/exports on the PC that opens the report (default: this project's folder)")
def powerbi(data_folder):
    """Generate the Power BI project (powerbi/Algotrader/Algotrader.pbip)."""
    from src.reporting.powerbi import build_powerbi_project

    folder = data_folder or str(Path(__file__).resolve().parent / "data" / "exports")
    pbip = build_powerbi_project(folder)
    console.print(f"[green]Power BI project:[/green] {pbip}")
    console.print(f"Data folder set to: {folder}")


if __name__ == "__main__":
    cli()
