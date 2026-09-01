"""Gym-style wrapper over :class:`Simulation` for training.

Minimal surface: ``reset(seed) -> None`` then ``run_episode(scheduler, steps)``
which drives one :class:`Simulation` with a supplied scheduler instance and
returns the episode's average ground-truth reward. Deterministic per seed.
"""

from __future__ import annotations

from ..models.core import RFEnvironmentConfig, ReceiverConfig
from ..simulation.engine import Simulation


class SimEnv:
    def __init__(
        self,
        env_config: RFEnvironmentConfig,
        receiver_config: ReceiverConfig | None = None,
        ew_effects: list | None = None,
    ) -> None:
        self.env_config = env_config
        self.receiver_config = receiver_config or ReceiverConfig()
        self.ew_effects = ew_effects

    def run_episode(self, scheduler_instance, steps: int, *, seed: int) -> dict:
        cfg = self.env_config.model_copy(update={"seed": int(seed)})
        sim = Simulation(
            env_config=cfg,
            receiver_config=self.receiver_config,
            scheduler_name=getattr(scheduler_instance, "name", "custom"),
            scheduler_instance=scheduler_instance,
            ew_effects=self.ew_effects,
        )
        sim.run(steps)
        if hasattr(scheduler_instance, "end_episode"):
            scheduler_instance.end_episode()
        m = sim.metrics_snapshot()
        return {
            "average_reward": m.average_reward,
            "probability_of_detection": m.probability_of_detection,
            "interception_ratio": m.interception_ratio,
            "high_priority_detection_rate": m.high_priority_detection_rate,
            "missed_opportunity_count": m.missed_opportunity_count,
            "steps": m.steps,
        }
