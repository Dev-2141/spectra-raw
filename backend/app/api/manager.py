"""Process-wide simulation manager.

Holds the single active :class:`Simulation`, guards it with a lock, and builds
the JSON snapshots the frontend renders.
"""

from __future__ import annotations

import threading

import numpy as np

from ..models.core import (
    EpisodeResult,
    RFEnvironmentConfig,
    ReceiverConfig,
    ResetRequest,
    TrainingReport,
    TrainRequest,
)
from ..schedulers.registry import create_scheduler, list_schedulers
from ..simulation.engine import Simulation

WATERFALL_SLOTS = 160
SCAN_PATH_LEN = 240


class SimulationManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sim: Simulation | None = None
        self._scheduler_name = "round_robin"
        self._scheduler_params: dict = {}
        self._env_config = RFEnvironmentConfig()
        self._receiver_config = ReceiverConfig()
        self.reset(ResetRequest())

    # ------------------------------------------------------------------ #
    @property
    def sim(self) -> Simulation:
        if self._sim is None:  # pragma: no cover - constructed in __init__
            self.reset(ResetRequest())
        assert self._sim is not None
        return self._sim

    def reset(self, req: ResetRequest) -> dict:
        with self._lock:
            if req.environment is not None:
                self._env_config = req.environment
            if req.receiver is not None:
                self._receiver_config = req.receiver
            self._scheduler_name = req.scheduler or self._scheduler_name
            self._scheduler_params = req.scheduler_params or {}

            self._sim = Simulation(
                env_config=self._env_config,
                receiver_config=self._receiver_config,
                scheduler_name=self._scheduler_name,
                scheduler_params=self._scheduler_params,
            )
            return self.state()

    def step(self, count: int = 1) -> dict:
        with self._lock:
            results = self.sim.run(count) if count > 1 else [self.sim.step()]
            last = results[-1] if results else None
            state = self.state()
            state["last_step"] = last.model_dump() if last else None
            state["steps_executed"] = len(results)
            return state

    def run(self, steps: int, scheduler: str | None, params: dict, reset: bool) -> dict:
        with self._lock:
            if reset:
                self.reset(
                    ResetRequest(
                        environment=self._env_config,
                        receiver=self._receiver_config,
                        scheduler=scheduler or self._scheduler_name,
                        scheduler_params=params or self._scheduler_params,
                    )
                )
            elif scheduler and scheduler != self._scheduler_name:
                raise ValueError(
                    "Cannot switch scheduler mid-run without reset=true."
                )
            results = self.sim.run(steps)
            state = self.state()
            state["steps_executed"] = len(results)
            state["last_step"] = results[-1].model_dump() if results else None
            state["metrics"] = self.sim.metrics_snapshot().model_dump()
            return state

    # ------------------------------------------------------------------ #
    def train(self, req: TrainRequest) -> dict:
        """Run a scheduler over multiple episodes, persisting its learned state.

        A single scheduler instance is carried across episodes; only the
        environment / receiver / metrics are rebuilt each episode.
        """
        with self._lock:
            base_seed = self._env_config.seed
            scheduler = create_scheduler(
                req.scheduler,
                self._env_config.num_bands,
                np.random.default_rng(base_seed + 202),
                req.scheduler_params,
            )

            episodes: list[EpisodeResult] = []
            for ep in range(req.episodes):
                seed = base_seed + (ep * 7919 if req.vary_seed else 0)
                env_cfg = self._env_config.model_copy(update={"seed": seed})
                sim = Simulation(
                    env_config=env_cfg,
                    receiver_config=self._receiver_config,
                    scheduler_name=req.scheduler,
                    scheduler_params=req.scheduler_params,
                    scheduler_instance=scheduler,
                )
                sim.run(req.steps_per_episode)
                if hasattr(scheduler, "end_episode"):
                    scheduler.end_episode()

                m = sim.metrics_snapshot()
                episodes.append(
                    EpisodeResult(
                        episode=ep + 1,
                        seed=seed,
                        steps=m.steps,
                        total_reward=m.total_reward,
                        average_reward=m.average_reward,
                        probability_of_detection=m.probability_of_detection,
                        interception_ratio=m.interception_ratio,
                        high_priority_detection_rate=m.high_priority_detection_rate,
                        missed_opportunity_count=m.missed_opportunity_count,
                        epsilon=round(float(getattr(scheduler, "epsilon", None)), 4)
                        if getattr(scheduler, "epsilon", None) is not None
                        else None,
                        q_states=len(getattr(scheduler, "q", {})) or None,
                        q_updates=getattr(scheduler, "updates", None) or None,
                    )
                )

            first = episodes[0].average_reward
            last = episodes[-1].average_reward
            best = max(range(len(episodes)), key=lambda i: episodes[i].average_reward)
            report = TrainingReport(
                scheduler=req.scheduler,
                episodes=req.episodes,
                steps_per_episode=req.steps_per_episode,
                episode_results=episodes,
                first_episode_avg_reward=first,
                last_episode_avg_reward=last,
                reward_improvement=round(last - first, 4),
                best_episode=best + 1,
            )
            return report.model_dump()

    # ------------------------------------------------------------------ #
    def state(self) -> dict:
        with self._lock:
            sim = self.sim
            env = sim.env
            t = min(sim.t, env.num_time_slots - 1)

            lo = max(0, t - WATERFALL_SLOTS + 1)
            power_window = env.power_db[lo : t + 1]
            occ_window = env.occupancy[lo : t + 1]

            scan_path = [
                {
                    "time_slot": r.time_slot,
                    "band": r.detection.band,
                    "scanned_band": r.decision.selected_band,
                    "detected": r.detection.detected,
                    "false_alarm": r.detection.false_alarm,
                    "true_active": r.detection.true_active,
                    "reward": r.reward,
                }
                for r in sim.history[-SCAN_PATH_LEN:]
            ]

            reward_series = [
                {"time_slot": r.time_slot, "reward": r.reward}
                for r in sim.history[-SCAN_PATH_LEN:]
            ]

            metrics = sim.metrics_snapshot()

            return {
                "product": "SPECTRA-SCAN AI",
                "mode": "simulation-only / receive-only",
                "running": not sim.done,
                "done": sim.done,
                "time_slot": sim.t,
                "max_slots": env.num_time_slots,
                "scheduler": sim.scheduler_name,
                "available_schedulers": list_schedulers(),
                "environment": {
                    "num_bands": env.num_bands,
                    "num_time_slots": env.num_time_slots,
                    "noise_floor_db": env.noise_floor_db,
                    "seed": sim.env_config.seed,
                    "emitter_density": sim.env_config.emitter_density,
                    "occupancy_percentage": round(env.occupancy_percentage(), 4),
                    "emitter_count": len(env.emitters),
                },
                "receiver": {
                    "current_band": sim.receiver.state.current_band,
                    "dwell_slots": sim.receiver_config.dwell_slots,
                    "retune_delay_slots": sim.receiver_config.retune_delay_slots,
                    "detection_threshold_db": sim.receiver_config.detection_threshold_db,
                    "scan_window": sim.receiver_config.scan_window,
                    "total_scans": sim.receiver.state.total_scans,
                },
                "emitters": [e.model_dump() for e in env.emitters],
                "bands": [b.model_dump() for b in env.bands],
                "spectrum": {
                    "time_slot": t,
                    "power_db": _round_list(env.power_db[t].tolist(), 2),
                    "active": occ_window[-1].astype(int).tolist()
                    if len(occ_window)
                    else [0] * env.num_bands,
                    "threshold_db": env.noise_floor_db
                    + sim.receiver_config.detection_threshold_db,
                    "threat_prior": _round_list(sim.band_threat_prior.tolist(), 3),
                    "predicted_activity": _round_list(
                        sim.predicted_activity.tolist(), 3
                    ),
                },
                "waterfall": {
                    "start_slot": lo,
                    "power_db": [_round_list(row, 2) for row in power_window.tolist()],
                    "active": occ_window.astype(int).tolist(),
                },
                "scan_path": scan_path,
                "reward_series": reward_series,
                "metrics": metrics.model_dump(),
            }


def _round_list(values, ndigits: int):
    return [round(float(v), ndigits) for v in values]


_MANAGER: SimulationManager | None = None
_MANAGER_LOCK = threading.Lock()


def get_manager() -> SimulationManager:
    global _MANAGER
    if _MANAGER is None:
        with _MANAGER_LOCK:
            if _MANAGER is None:
                _MANAGER = SimulationManager()
    return _MANAGER
