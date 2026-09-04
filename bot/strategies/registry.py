from __future__ import annotations

from bot.strategies.base import Strategy
from bot.strategies.noop import NoopStrategy

_REGISTRY: dict[str, type] = {
    "noop": NoopStrategy,
}


def register(strategy_id: str, cls: type) -> None:
    _REGISTRY[strategy_id] = cls


def load_strategies(ids: list[str]) -> list[Strategy]:
    loaded: list[Strategy] = []
    for strategy_id in ids:
        if strategy_id not in _REGISTRY:
            raise KeyError(
                f"Unknown strategy '{strategy_id}'. "
                "Register it in bot.strategies.registry after adding a condition file."
            )
        loaded.append(_REGISTRY[strategy_id]())
    return loaded
