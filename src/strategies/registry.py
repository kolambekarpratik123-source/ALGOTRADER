"""Strategy factory — pick strategy by name."""

from src.strategies.base import Strategy
from src.strategies.composite import CompositeStrategy
from src.strategies.ma_crossover import MovingAverageCrossover
from src.strategies.macd import MACDStrategy
from src.strategies.rsi import RSIStrategy

STRATEGIES: dict[str, type[Strategy]] = {
    "ma_crossover": MovingAverageCrossover,
    "rsi": RSIStrategy,
    "macd": MACDStrategy,
}


def get_strategy(name: str) -> Strategy:
    if name == "composite":
        return CompositeStrategy(
            strategies=[
                MovingAverageCrossover(),
                RSIStrategy(),
                MACDStrategy(),
            ],
            min_agree=2,
        )
    cls = STRATEGIES.get(name)
    if cls is None:
        available = ", ".join(list(STRATEGIES.keys()) + ["composite"])
        raise ValueError(f"Unknown strategy '{name}'. Available: {available}")
    return cls()


def list_strategies() -> list[str]:
    return list(STRATEGIES.keys()) + ["composite"]
