"""Scheduler registry.

Names exposed to the API / UI:
    round_robin, random, priority, epsilon_bandit, ucb_bandit, thompson,
    q_learning, contextual_bandit, dqn (torch), drqn (torch)
"""

from __future__ import annotations

from .base import BaseScheduler
from .baseline import RandomScheduler, RoundRobinScheduler
from .learning import ContextualBanditScheduler, DQNScheduler, DRQNScheduler, torch_available
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
    ContextualBanditScheduler.name: ContextualBanditScheduler,
    "dqn": DQNScheduler,
    "drqn": DRQNScheduler,
}

# Schedulers that carry learned state worth training across episodes.
LEARNING_SCHEDULERS = {
    EpsilonGreedyBanditScheduler.name,
    UCB1BanditScheduler.name,
    ThompsonSamplingScheduler.name,
    QLearningScheduler.name,
    PriorityScoreScheduler.name,
    ContextualBanditScheduler.name,
    "dqn",
    "drqn",
}

# name -> unmet requirement (empty when available)
_TORCH_SCHEDULERS = {"dqn", "drqn"}


def scheduler_requirements() -> dict[str, list[str]]:
    torch_ok = torch_available()
    return {
        name: ([] if (name not in _TORCH_SCHEDULERS or torch_ok) else ["torch"])
        for name in SCHEDULER_REGISTRY
    }


def list_schedulers() -> list[str]:
    return list(SCHEDULER_REGISTRY.keys())


def available_schedulers() -> list[str]:
    reqs = scheduler_requirements()
    return [n for n, missing in reqs.items() if not missing]


def create_scheduler(
    name: str, num_bands: int, rng, params: dict | None = None
) -> BaseScheduler:
    if name not in SCHEDULER_REGISTRY:
        raise KeyError(
            f"Unknown scheduler '{name}'. Available: {', '.join(SCHEDULER_REGISTRY)}"
        )
    return SCHEDULER_REGISTRY[name](num_bands=num_bands, rng=rng, params=params)
