"""Async RL training jobs + checkpointing.

Works for any learning scheduler. ``contextual_bandit`` trains with pure NumPy;
``dqn`` needs torch (falls through to a clear error). A single scheduler
instance is carried across episodes so it accumulates learned state; the
learning curve is per-episode average ground-truth reward.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from ..config import get_settings
from ..models.core import RFEnvironmentConfig, ReceiverConfig, RLJob, RLTrainRequest
from ..schedulers.registry import LEARNING_SCHEDULERS, create_scheduler
from ..simulation.presets import get_preset
from .curriculum import curriculum_stages
from .envs import SimEnv


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rl_dir() -> Path:
    d = get_settings().data_dir / "rl"
    d.mkdir(parents=True, exist_ok=True)
    return d


class RLManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, RLJob] = {}
        self._promoted: dict[str, str] = {}  # scheduler -> checkpoint path

    # ------------------------------------------------------------------ #
    def submit(self, req: RLTrainRequest, actor: str = "system") -> RLJob:
        if req.scheduler not in LEARNING_SCHEDULERS:
            raise ValueError(f"'{req.scheduler}' is not a learning scheduler")
        # fail fast if the scheduler can't be constructed (e.g. torch missing)
        create_scheduler(req.scheduler, 8, np.random.default_rng(0), req.scheduler_params)

        job_id = f"rl_{uuid.uuid4().hex[:10]}"
        stages = curriculum_stages() if req.curriculum else []
        job = RLJob(
            job_id=job_id,
            scheduler=req.scheduler,
            status="queued",
            created_at=_utc(),
            updated_at=_utc(),
            episodes=req.episodes if not req.curriculum else req.episodes * len(stages),
            episodes_done=0,
            curriculum=req.curriculum,
        )
        with self._lock:
            self._jobs[job_id] = job
        threading.Thread(
            target=self._run, args=(job_id, req, stages), name=f"rl-{job_id}", daemon=True
        ).start()
        return job

    def list_jobs(self) -> list[RLJob]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def get_job(self, job_id: str) -> RLJob:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            return self._jobs[job_id]

    def promote(self, job_id: str) -> RLJob:
        with self._lock:
            job = self._jobs[job_id]
            if not job.checkpoint:
                raise ValueError("job has no checkpoint to promote")
            job.promoted = True
            self._promoted[job.scheduler] = job.checkpoint
            for other in self._jobs.values():
                if other.job_id != job_id and other.scheduler == job.scheduler:
                    other.promoted = False
            return job

    def promoted_instance(self, scheduler: str, num_bands: int, rng):
        path = self._promoted.get(scheduler)
        if not path or not Path(path).is_file():
            return None
        inst = create_scheduler(scheduler, num_bands, rng, {})
        try:
            with open(path, "r", encoding="utf-8") as fh:
                inst.load_state_dict(json.load(fh))
        except Exception:
            return None
        return inst

    # ------------------------------------------------------------------ #
    def _config_for(self, req: RLTrainRequest, stage: str | None):
        if stage:
            return get_preset(stage)
        if req.scenario_id:
            from ..simulation.scenario import get_scenario_store

            scn = get_scenario_store().get(req.scenario_id)
            return scn.environment.model_copy(deep=True), scn.receiver.model_copy(deep=True)
        return (
            RFEnvironmentConfig(num_bands=48, num_time_slots=req.steps_per_episode + 20),
            ReceiverConfig(),
        )

    def _run(self, job_id: str, req: RLTrainRequest, stages: list[str]) -> None:
        job = self._jobs[job_id]
        job.status = "running"
        job.updated_at = _utc()
        try:
            rng = np.random.default_rng(req.base_seed)
            # one scheduler instance carried across every episode / stage
            probe_cfg, _ = self._config_for(req, stages[0] if stages else None)
            scheduler = create_scheduler(
                req.scheduler, probe_cfg.num_bands, rng, req.scheduler_params
            )
            plan = stages or [None]
            best = None
            for stage in plan:
                env_cfg, rcv_cfg = self._config_for(req, stage)
                # rebuild scheduler if the band count changed between stages
                if scheduler.num_bands != env_cfg.num_bands:
                    scheduler = create_scheduler(
                        req.scheduler, env_cfg.num_bands, rng, req.scheduler_params
                    )
                env = SimEnv(env_cfg, rcv_cfg)
                stage_curve: list[float] = []
                for ep in range(req.episodes):
                    seed = req.base_seed + len(job.learning_curve) * 7919
                    res = env.run_episode(scheduler, req.steps_per_episode, seed=seed)
                    ar = float(res["average_reward"])
                    job.learning_curve.append(round(ar, 4))
                    stage_curve.append(ar)
                    job.episodes_done += 1
                    job.final_avg_reward = round(ar, 4)
                    best = ar if best is None else max(best, ar)
                    job.best_avg_reward = round(best, 4)
                    job.stage = stage
                    job.updated_at = _utc()
                if stage is not None:
                    job.curriculum_stages.append(
                        {
                            "stage": stage,
                            "first": round(stage_curve[0], 4),
                            "last": round(stage_curve[-1], 4),
                            "mean": round(float(np.mean(stage_curve)), 4),
                        }
                    )

            job.checkpoint = self._save_checkpoint(job_id, scheduler)
            job.status = "done"
        except Exception as exc:  # pragma: no cover - defensive
            job.status = "failed"
            job.error = f"{type(exc).__name__}: {exc}"
        job.updated_at = _utc()

    def _save_checkpoint(self, job_id: str, scheduler) -> str | None:
        sd = getattr(scheduler, "state_dict", None)
        if sd is None:
            return None
        state = sd()
        out = _rl_dir() / job_id
        out.mkdir(parents=True, exist_ok=True)
        try:
            path = out / "checkpoint.json"
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(state, fh)
            return str(path)
        except TypeError:  # torch tensors -> torch.save
            try:
                import torch

                path = out / "checkpoint.pt"
                torch.save(state, path)
                return str(path)
            except Exception:
                return None


_manager: RLManager | None = None


def get_rl_manager() -> RLManager:
    global _manager
    if _manager is None:
        _manager = RLManager()
    return _manager


def _reset_for_tests() -> None:
    global _manager
    _manager = None
