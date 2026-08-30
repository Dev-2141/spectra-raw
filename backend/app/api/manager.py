"""Process-wide simulation manager.

Holds the single active :class:`Simulation`, guards it with a lock, and builds
the JSON snapshots the frontend renders.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

import numpy as np

from ..comparison.engine import compare_strategies
from ..dataset.generator import build_dataset
from ..dataset.store import get_store
from ..models.core import (
    ComparisonReport,
    ComparisonRequest,
    DatasetGenerateRequest,
    DatasetLoadRequest,
    DatasetMeta,
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


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class SimulationManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sim: Simulation | None = None
        self._scheduler_name = "round_robin"
        self._scheduler_params: dict = {}
        self._env_config = RFEnvironmentConfig()
        self._receiver_config = ReceiverConfig()
        self._dataset_id: str | None = None
        self._last_comparison: ComparisonReport | None = None
        self._training_runs: list[TrainingReport] = []
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
                # Explicit env config exits dataset-replay mode.
                self._env_config = req.environment
                self._dataset_id = None
            if req.receiver is not None:
                self._receiver_config = req.receiver
            self._scheduler_name = req.scheduler or self._scheduler_name
            self._scheduler_params = req.scheduler_params or {}

            env_instance = None
            if self._dataset_id is not None:
                env_instance = get_store().build_replay_env(self._dataset_id)

            self._sim = Simulation(
                env_config=self._env_config,
                receiver_config=self._receiver_config,
                scheduler_name=self._scheduler_name,
                scheduler_params=self._scheduler_params,
                env_instance=env_instance,
            )
            return self.state()

    # ------------------------------------------------------------------ #
    # Dataset lab
    # ------------------------------------------------------------------ #
    def generate_dataset(self, req: DatasetGenerateRequest) -> dict:
        with self._lock:
            cfg = req.config or self._env_config
            meta, arrays = build_dataset(cfg, name=req.name)
            meta = get_store().save(meta, arrays)
            return meta.model_dump()

    def list_datasets(self) -> list[dict]:
        return [m.model_dump() for m in get_store().list()]

    def get_dataset(self, dataset_id: str) -> dict:
        return get_store().get(dataset_id).model_dump()

    def dataset_stats(self, dataset_id: str) -> dict:
        return get_store().get(dataset_id).stats.model_dump()

    def load_dataset(self, dataset_id: str, req: DatasetLoadRequest) -> dict:
        with self._lock:
            store = get_store()
            store.get(dataset_id)  # raises KeyError if missing
            self._dataset_id = dataset_id
            self._env_config = store.config_for(dataset_id)
            if req.receiver is not None:
                self._receiver_config = req.receiver
            self._scheduler_name = req.scheduler or self._scheduler_name
            self._scheduler_params = req.scheduler_params or {}

            self._sim = Simulation(
                env_config=self._env_config,
                receiver_config=self._receiver_config,
                scheduler_name=self._scheduler_name,
                scheduler_params=self._scheduler_params,
                env_instance=store.build_replay_env(dataset_id),
            )
            state = self.state()
            state["loaded_dataset"] = dataset_id
            return state

    # ------------------------------------------------------------------ #
    # Strategy comparison
    # ------------------------------------------------------------------ #
    def run_comparison(self, req: ComparisonRequest) -> dict:
        with self._lock:
            unknown = [s for s in req.schedulers if s not in list_schedulers()]
            if unknown:
                raise KeyError(f"unknown scheduler(s): {', '.join(unknown)}")

            env_factory = None
            replayed = None
            if self._dataset_id is not None:
                ds_id = self._dataset_id
                replayed = ds_id
                env_factory = lambda: get_store().build_replay_env(ds_id)  # noqa: E731
                env_config = get_store().config_for(ds_id)
            else:
                env_config = self._env_config
                if req.seed is not None:
                    env_config = env_config.model_copy(update={"seed": req.seed})

            report = compare_strategies(
                env_config=env_config,
                receiver_config=self._receiver_config,
                schedulers=req.schedulers,
                steps=req.steps,
                series_points=req.series_points,
                scheduler_params=req.scheduler_params,
                env_factory=env_factory,
                replayed_dataset=replayed,
            )
            self._last_comparison = report
            return report.model_dump()

    def last_comparison(self) -> ComparisonReport | None:
        return self._last_comparison

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
                # Pass no environment so replay-mode (loaded dataset) is preserved.
                self.reset(
                    ResetRequest(
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
            self._training_runs.append(report)
            del self._training_runs[:-25]
            return report.model_dump()

    def training_runs(self) -> list[dict]:
        with self._lock:
            return [r.model_dump() for r in reversed(self._training_runs)]

    def last_training(self) -> dict | None:
        with self._lock:
            return self._training_runs[-1].model_dump() if self._training_runs else None

    # ------------------------------------------------------------------ #
    def explainability_log(self, limit: int = 200) -> list[dict]:
        """Recent scheduler decisions with their reasoning, newest last."""
        with self._lock:
            rows: list[dict] = []
            for r in self.sim.history[-limit:]:
                d, det = r.decision, r.detection
                if det.detected and det.true_active:
                    outcome = "hit"
                elif det.false_alarm:
                    outcome = "false_alarm"
                elif det.true_active:
                    outcome = "miss"
                else:
                    outcome = "empty"
                rows.append(
                    {
                        "time_slot": r.time_slot,
                        "scheduler": d.scheduler,
                        "selected_band": d.selected_band,
                        "confidence": d.confidence,
                        "predicted_active": d.predicted_active,
                        "reward": r.reward,
                        "outcome": outcome,
                        "reasons": d.reasons,
                        "alternatives": d.alternatives,
                        "explanation": d.explanation,
                        "reward_breakdown": r.reward_breakdown,
                    }
                )
            return rows

    def run_report(self) -> dict:
        """Snapshot of the current run: config + final metrics + recent decisions."""
        with self._lock:
            sim = self.sim
            m = sim.metrics_snapshot()
            return {
                "product": "SPECTRA-SCAN AI",
                "mode": "simulation-only / receive-only",
                "generated_at": _utc_now(),
                "scheduler": sim.scheduler_name,
                "dataset_id": self._dataset_id,
                "replay_mode": bool(getattr(sim.env, "replayed", False)),
                "environment_config": self._env_config.model_dump(),
                "receiver_config": self._receiver_config.model_dump(),
                "time_slot": sim.t,
                "max_slots": sim.env.num_time_slots,
                "steps_run": len(sim.history),
                "metrics": m.model_dump(),
                "recent_decisions": self.explainability_log(limit=10),
            }

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
                "dataset_id": self._dataset_id,
                "replay_mode": bool(getattr(env, "replayed", False)),
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
