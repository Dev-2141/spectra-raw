"""Scheduler registry.

Names exposed to the API / UI:
    round_robin, random, priority, epsilon_bandit, ucb_bandit, thompson, q_learning
"""

from __future__ import annotations

from .base import BaseScheduler
from .baseline import RandomScheduler, RoundRobinScheduler
from .qlearning import QLearningScheduler
from .smart import (
    EpsilonGreedyBanditScheduler,
    PriorityScoreScheduler,
    ThompsonSamplingScheduler,
    UCB1BanditScheduler,
)

SCHEDULER_REGISTRY: dict[str, type[BaseScheduler]] = {
    RoundRobinScheduler.name: RoundRobinScheduler,
    RandomScheduler.name: RandomScheduler,
    PriorityScoreScheduler.name: PriorityScoreScheduler,
    EpsilonGreedyBanditScheduler.name: EpsilonGreedyBanditScheduler,
    UCB1BanditScheduler.name: UCB1BanditScheduler,
    ThompsonSamplingScheduler.name: ThompsonSamplingScheduler,
    QLearningScheduler.name: QLearningScheduler,
}

# Schedulers that carry learned state worth training across episodes.
LEARNING_SCHEDULERS = {
    EpsilonGreedyBanditScheduler.name,
    UCB1BanditScheduler.name,
    ThompsonSamplingScheduler.name,
    QLearningScheduler.name,
    PriorityScoreScheduler.name,
}


def list_schedulers() -> list[str]:
    return list(SCHEDULER_REGISTRY.keys())


def create_scheduler(
    name: str, num_bands: int, rng, params: dict | None = None
) -> BaseScheduler:
    if name not in SCHEDULER_REGISTRY:
        raise KeyError(
            f"Unknown scheduler '{name}'. Available: {', '.join(SCHEDULER_REGISTRY)}"
        )
    return SCHEDULER_REGISTRY[name](num_bands=num_bands, rng=rng, params=params)
