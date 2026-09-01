"""Process-wide simulation manager.

Holds the single active :class:`Simulation`, guards it with a lock, and builds
the JSON snapshots the frontend renders.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

import numpy as np

from ..audit.log import audit
from ..comparison.engine import compare_strategies
from ..dataset.generator import build_dataset
from ..dataset.store import get_store
from ..hardware.manager import get_hardware_manager
from ..hardware.recordings import get_recording_meta, list_recordings
from ..modes.manager import get_mode_manager
from ..simulation.live_env import LiveRFEnvironment
from ..tasking.state import get_tasking_state
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
from ..simulation.presets import get_preset, list_presets

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
        self._preset_name: str | None = None
        self._scenario_name: str | None = None
        self._effect_specs: list = []
        self._last_comparison: ComparisonReport | None = None
        self._last_montecarlo = None
        self._training_runs: list[TrainingReport] = []
        self.reset(ResetRequest())

    # ------------------------------------------------------------------ #
    def presets(self) -> list[dict]:
        return list_presets()

    # ------------------------------------------------------------------ #
    @property
    def sim(self) -> Simulation:
        if self._sim is None:  # pragma: no cover - constructed in __init__
            self.reset(ResetRequest())
        assert self._sim is not None
        return self._sim

    def reset(self, req: ResetRequest) -> dict:
        with self._lock:
            # Live-ES mode with a running receive-only source: drive the same
            # Simulation off DSP observations instead of synthetic ground truth.
            if get_mode_manager().mode == "live_es" and get_hardware_manager().running:
                return self._build_live_sim(req)

            if req.preset is not None:
                # A preset is an explicit base config -> exits replay mode and
                # clears any loaded scenario's EW effects.
                env_cfg, rcv_cfg = get_preset(req.preset)
                self._env_config = env_cfg
                self._receiver_config = rcv_cfg
                self._preset_name = req.preset
                self._scenario_name = None
                self._effect_specs = []
                self._dataset_id = None
            if req.environment is not None:
                # Explicit env config exits dataset-replay mode.
                self._env_config = req.environment
                self._dataset_id = None
                self._scenario_name = None
                self._effect_specs = []
                if req.preset is None:
                    self._preset_name = None
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
                protected_bands=get_tasking_state().protected_bands,
                on_override=self._on_protected_override,
                on_step_hook=self._online_step,
                tasking_weights=get_tasking_state().band_weights(
                    self._env_config.num_bands
                ),
                ew_effects=(self._effect_specs or None) if env_instance is None else None,
            )
            return self.state()

    # ------------------------------------------------------------------ #
    def load_scenario(self, scenario_id: str) -> dict:
        from ..simulation.scenario import get_scenario_store

        from ..df.nodes import default_layout, get_node_registry

        scn = get_scenario_store().get(scenario_id)
        with self._lock:
            self._env_config = scn.environment.model_copy(deep=True)
            self._receiver_config = scn.receiver.model_copy(deep=True)
            self._effect_specs = [e.model_copy(deep=True) for e in scn.effects]
            self._scenario_name = scn.name
            self._preset_name = scn.name
            self._dataset_id = None
            get_node_registry().set_nodes(
                [n.model_copy(deep=True) for n in scn.df_nodes] or default_layout()
            )
            self._df_cache = None
            self._sim = Simulation(
                env_config=self._env_config,
                receiver_config=self._receiver_config,
                scheduler_name=self._scheduler_name,
                scheduler_params=self._scheduler_params,
                protected_bands=get_tasking_state().protected_bands,
                on_override=self._on_protected_override,
                on_step_hook=self._online_step,
                tasking_weights=get_tasking_state().band_weights(
                    self._env_config.num_bands
                ),
                ew_effects=self._effect_specs or None,
            )
            st = self.state()
            st["loaded_scenario"] = scenario_id
            return st

    def run_montecarlo(self, req) -> dict:
        from ..comparison.montecarlo import run_montecarlo
        from ..simulation.scenario import get_scenario_store

        with self._lock:
            if req.scenario_id:
                scn = get_scenario_store().get(req.scenario_id)
                env = scn.environment
                rcv = scn.receiver
                effects = list(scn.effects)
                sc_name = scn.name
            else:
                env = req.environment or self._env_config
                rcv = req.receiver or self._receiver_config
                effects = list(req.effects) or list(self._effect_specs)
                sc_name = self._scenario_name or "current"

            seeds = list(req.seeds) or [
                req.base_seed + i * 101 for i in range(req.n_seeds)
            ]
            report = run_montecarlo(
                environment=env,
                receiver=rcv,
                effects=effects,
                schedulers=req.schedulers,
                seeds=seeds,
                steps=req.steps,
                scenario_id=req.scenario_id,
                scenario_name=sc_name,
            )
            self._last_montecarlo = report
            return report.model_dump()

    def last_montecarlo(self):
        return self._last_montecarlo

    # ------------------------------------------------------------------ #
    # Signal analysis: tracks / anomaly / forecast / alerts (Step 4)
    # ------------------------------------------------------------------ #
    def _analysis_snapshot(self) -> dict:
        from ..alerting.engine import get_alert_store
        from ..analysis.anomaly import detect as detect_anomaly
        from ..analysis.forecast import forecast_tracks
        from ..analysis.tracks import extract_tracks
        from ..library.store import get_library
        from ..tasking.state import get_tasking_state

        with self._lock:
            sim = self.sim
            store = get_alert_store()
            if getattr(self, "_analysis_sim_id", None) != id(sim):
                store.reset()
                self._analysis_sim_id = id(sim)
                self._analysis_cache = None

            up_to = min(sim.t, sim.env.num_time_slots - 1)
            cache = getattr(self, "_analysis_cache", None)
            if cache and cache["t"] == up_to:
                return cache

            lib = get_library().list()
            track_objs = extract_tracks(sim.env, up_to, library_entries=lib)
            tracks = [o.to_dict(up_to) for o in track_objs]
            anomaly = detect_anomaly(sim.env, up_to)
            forecasts = forecast_tracks(track_objs, up_to)
            new_alerts = store.evaluate(
                tracks, anomaly, get_tasking_state().alert_rules
            )
            snap = {
                "t": up_to,
                "tracks": tracks,
                "anomaly": anomaly,
                "forecast": forecasts,
                "new_alerts": [a.model_dump() for a in new_alerts],
            }
            self._analysis_cache = snap
            return snap

    def tracks(self) -> dict:
        snap = self._analysis_snapshot()
        return {"tracks": snap["tracks"], "time_slot": snap["t"]}

    def track(self, track_id: str) -> dict:
        for tr in self._analysis_snapshot()["tracks"]:
            if tr["track_id"] == track_id:
                return tr
        raise KeyError(track_id)

    def anomaly(self) -> dict:
        return self._analysis_snapshot()["anomaly"]

    def forecast(self) -> dict:
        snap = self._analysis_snapshot()
        return {"forecast": snap["forecast"], "time_slot": snap["t"]}

    def alerts(self, state: str | None = None) -> dict:
        from ..alerting.engine import get_alert_store

        self._analysis_snapshot()  # refresh
        store = get_alert_store()
        return {
            "alerts": [a.model_dump() for a in store.list(state)],
            "unacked": store.unacked_count(),
        }

    def set_alert_state(self, alert_id: str, state: str) -> dict:
        from ..alerting.engine import get_alert_store

        return get_alert_store().set_state(alert_id, state).model_dump()

    def unacked_alert_count(self) -> int:
        from ..alerting.engine import get_alert_store

        return get_alert_store().unacked_count()

    # --- tasking (watch lists + alert rules) ------------------------- #
    def watch_lists(self) -> dict:
        from ..tasking.state import get_tasking_state

        return {
            "watch_lists": [w.model_dump() for w in get_tasking_state().watch_lists]
        }

    def set_watch_lists(self, items) -> dict:
        from ..tasking.state import get_tasking_state

        out = get_tasking_state().set_watch_lists(items)
        with self._lock:
            self._sim._tasking_weights = get_tasking_state().band_weights(
                self._sim.env.num_bands
            )
        return {"watch_lists": [w.model_dump() for w in out]}

    def alert_rules(self) -> dict:
        from ..tasking.state import get_tasking_state

        return {
            "alert_rules": [r.model_dump() for r in get_tasking_state().alert_rules]
        }

    def set_alert_rules(self, items) -> dict:
        from ..tasking.state import get_tasking_state

        out = get_tasking_state().set_alert_rules(items)
        return {"alert_rules": [r.model_dump() for r in out]}

    # --- library -------------------------------------------------- #
    def library(self) -> dict:
        from ..library.store import get_library

        return {"entries": [e.model_dump() for e in get_library().list()]}

    def library_revisions(self, entry_id: str) -> dict:
        from ..library.store import get_library

        return {
            "revisions": [r.model_dump() for r in get_library().revisions(entry_id)]
        }

    # ------------------------------------------------------------------ #
    # Direction finding / geolocation (Step 5)
    # ------------------------------------------------------------------ #
    def _df_snapshot(self) -> dict:
        from ..df.engine import DFEngine, df_health, df_summary
        from ..df.nodes import get_node_registry

        with self._lock:
            sim = self.sim
            if not hasattr(self, "_df_engine"):
                self._df_engine = DFEngine()
            if getattr(self, "_df_sim_id", None) != id(sim):
                self._df_engine.reset(id(sim))
                self._df_sim_id = id(sim)
                self._df_cache = None

            up_to = min(sim.t, sim.env.num_time_slots - 1)
            cache = getattr(self, "_df_cache", None)
            if cache and cache["t"] == up_to:
                return cache

            tracks = self._analysis_snapshot()["tracks"]
            nodes = get_node_registry().get_nodes()
            fixes = self._df_engine.compute(
                sim.env, tracks, nodes, sim.env_config.seed, up_to
            )
            snap = {
                "t": up_to,
                "fixes": [f.model_dump() for f in fixes],
                "health": df_health(nodes, fixes),
                "summary": df_summary(nodes, fixes),
            }
            self._df_cache = snap
            return snap

    def df_nodes(self) -> dict:
        from ..df.nodes import get_node_registry

        return {"nodes": [n.model_dump() for n in get_node_registry().get_nodes()]}

    def set_df_nodes(self, nodes) -> dict:
        from ..df.nodes import get_node_registry

        out = get_node_registry().set_nodes(nodes)
        with self._lock:
            self._df_cache = None
        return {"nodes": [n.model_dump() for n in out]}

    def df_register(self, node) -> dict:
        from ..df.nodes import get_node_registry

        out = get_node_registry().register(node)
        with self._lock:
            self._df_cache = None
        return out.model_dump()

    def df_fixes(self) -> dict:
        snap = self._df_snapshot()
        return {"fixes": snap["fixes"], "summary": snap["summary"], "time_slot": snap["t"]}

    def df_fix(self, track_id: str) -> dict:
        snap = self._df_snapshot()
        for f in snap["fixes"]:
            if f["track_id"] == track_id:
                return {**f, "history": self._df_engine.history(track_id)}
        raise KeyError(track_id)

    def df_health(self) -> dict:
        return self._df_snapshot()["health"]

    def df_summary(self) -> dict:
        return self._df_snapshot()["summary"]

    def _df_summary_safe(self) -> dict:
        """Cheap DF summary for the polled state payload — never runs the engine."""
        from ..df.nodes import get_node_registry

        n = get_node_registry().count()
        cache = getattr(self, "_df_cache", None)
        if cache:
            return cache["summary"]
        return {"active": False, "n_nodes": n, "fixes": 0, "mean_cep_km": None}

    # ------------------------------------------------------------------ #
    # RL training / online learning / sim-to-real / explainability++ (Step 6)
    # ------------------------------------------------------------------ #
    def rl_submit(self, req) -> dict:
        from ..rl.train import get_rl_manager

        return get_rl_manager().submit(req).model_dump()

    def rl_jobs(self) -> dict:
        from ..rl.train import get_rl_manager

        return {"jobs": [j.model_dump() for j in get_rl_manager().list_jobs()]}

    def rl_job(self, job_id: str) -> dict:
        from ..rl.train import get_rl_manager

        return get_rl_manager().get_job(job_id).model_dump()

    def rl_promote(self, job_id: str) -> dict:
        from ..rl.train import get_rl_manager

        return get_rl_manager().promote(job_id).model_dump()

    # --- online learning ------------------------------------------- #
    def enable_online(self, req) -> dict:
        from ..rl.online import get_online_manager

        with self._lock:
            get_online_manager().enable(req.scheduler, req.margin, req.window)
            self._scheduler_name = req.scheduler
        self.reset(ResetRequest(scheduler=req.scheduler))
        return get_online_manager().status().model_dump()

    def disable_online(self) -> dict:
        from ..rl.online import get_online_manager

        return get_online_manager().disable().model_dump()

    def online_status(self) -> dict:
        from ..rl.online import get_online_manager

        return get_online_manager().status().model_dump()

    def _online_step(self, sim, result) -> None:
        from ..rl.online import get_online_manager
        from ..simulation.reward import compute_proxy_reward

        om = get_online_manager()
        if not om.enabled:
            return
        det = result.detection
        pol_r, _ = compute_proxy_reward(
            detected=det.detected, observed_active=det.true_active, retuned=result.retuned
        )
        ctx = sim._context()
        sh_band = om.shadow_decide(ctx)
        t = min(int(result.time_slot), sim.env.num_time_slots - 1)
        occ = getattr(sim.env, "occupancy_observed", sim.env.occupancy)
        sh_active = bool(occ[t, sh_band])
        sh_r, _ = compute_proxy_reward(
            detected=sh_active, observed_active=sh_active, retuned=False
        )
        if om.observe(int(result.time_slot), pol_r, sh_r) == "revert":
            from ..alerting.engine import get_alert_store
            from ..schedulers.registry import create_scheduler

            sim.scheduler = create_scheduler(
                "priority", sim.env.num_bands, np.random.default_rng(1234), {}
            )
            sim.scheduler_name = "priority"
            st = om.status()
            audit(
                "system", "online.guardrail.revert", detail=st.model_dump(),
                mode=get_mode_manager().mode,
            )
            get_alert_store().raise_alert(
                "online_guardrail", "critical",
                f"online policy '{om.active_scheduler}' auto-reverted to priority "
                f"at slot {st.reverted_at_slot} (policy EMA {st.policy_reward_ema} < "
                f"shadow {st.shadow_reward_ema} - margin {st.margin})",
            )

    def explain_policy(self) -> dict:
        with self._lock:
            sim = self.sim
            grid = sim.scheduler.policy_attribution(sim._context())
        if grid is None:
            return {
                "scheduler": sim.scheduler_name,
                "available": False,
                "detail": "this scheduler exposes no attribution grid",
            }
        grid["available"] = True
        return grid

    # --- sim-to-real ------------------------------------------- #
    def sim2real_calibrate(self, req) -> dict:
        from ..sim2real.calibrate import calibrate

        return calibrate(req.recording_id, req.name).model_dump()

    def sim2real_profiles(self) -> dict:
        from ..sim2real.calibrate import list_profiles

        return {"profiles": [p.model_dump() for p in list_profiles()]}

    def sim2real_gap(self, req) -> dict:
        from ..sim2real.gap import compute_gap

        return compute_gap(
            req.recording_id, req.profile_id, req.scheduler, req.steps, req.noise_shift_db
        ).model_dump()

    # ------------------------------------------------------------------ #
    # Dataset lab
    # ------------------------------------------------------------------ #
    def generate_dataset(self, req: DatasetGenerateRequest) -> dict:
        with self._lock:
            if req.config is not None:
                cfg = req.config
            elif req.preset is not None:
                cfg, _ = get_preset(req.preset)
            else:
                cfg = self._env_config
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
            self._preset_name = None
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
                protected_bands=get_tasking_state().protected_bands,
                on_override=self._on_protected_override,
                on_step_hook=self._online_step,
                tasking_weights=get_tasking_state().band_weights(
                    self._env_config.num_bands
                ),
            )
            state = self.state()
            state["loaded_dataset"] = dataset_id
            return state

    # ------------------------------------------------------------------ #
    def _build_live_sim(self, req: ResetRequest) -> dict:
        hw = get_hardware_manager()
        live_env = LiveRFEnvironment(hw.config, hw)
        self._dataset_id = None
        self._preset_name = None
        if req.receiver is not None:
            self._receiver_config = req.receiver
        self._scheduler_name = req.scheduler or self._scheduler_name
        self._scheduler_params = req.scheduler_params or {}
        self._env_config = RFEnvironmentConfig(
            num_bands=live_env.num_bands,
            num_time_slots=live_env.num_time_slots,
            seed=self._env_config.seed,
        )
        self._sim = Simulation(
            env_config=self._env_config,
            receiver_config=self._receiver_config,
            scheduler_name=self._scheduler_name,
            scheduler_params=self._scheduler_params,
            env_instance=live_env,
            protected_bands=get_tasking_state().protected_bands,
            on_override=self._on_protected_override,
                on_step_hook=self._online_step,
            tasking_weights=get_tasking_state().band_weights(live_env.num_bands),
        )
        return self.state()

    # --- hardware pass-through (Extension Step 2) ---------------------- #
    def hardware_status(self) -> dict:
        return get_hardware_manager().status().model_dump()

    def hardware_devices(self) -> list[dict]:
        return [d.model_dump() for d in get_hardware_manager().list_devices()]

    def configure_hardware(self, config) -> dict:
        return get_hardware_manager().configure(config).model_dump()

    def start_hardware(self, config=None) -> dict:
        return get_hardware_manager().start(config).model_dump()

    def stop_hardware(self) -> dict:
        return get_hardware_manager().stop().model_dump()

    def hardware_frame(self) -> dict | None:
        frame = get_hardware_manager().latest_frame()
        return frame.model_dump() if frame else None

    def hardware_frames(self, since: int = -1) -> dict:
        hw = get_hardware_manager()
        frames = hw.frames_since(since)
        return {
            "frames": [f.model_dump() for f in frames],
            "latest_seq": frames[-1].seq if frames else since,
            "observations": [o.model_dump() for o in hw.latest_observations()],
        }

    def start_recording(self, name: str | None) -> dict:
        return get_hardware_manager().start_recording(name)

    def stop_recording(self) -> dict:
        return get_hardware_manager().stop_recording().model_dump()

    def list_recordings(self) -> list[dict]:
        return [m.model_dump() for m in list_recordings()]

    def get_recording(self, recording_id: str) -> dict:
        return get_recording_meta(recording_id).model_dump()

    # ------------------------------------------------------------------ #
    def _on_protected_override(self, time_slot: int, original: int, band: int) -> None:
        """Audit callback fired when a scan is redirected off a protected band."""
        audit(
            "system",
            "protected_band.override",
            target=f"band {original}",
            detail={"time_slot": time_slot, "from": original, "to": band},
            mode=get_mode_manager().mode,
        )

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
            self._publish_and_record(state, results)
            return state

    # ------------------------------------------------------------------ #
    def _publish_and_record(self, state: dict, results: list) -> None:
        """Push a state event to /ws and record rows to the active session."""
        try:
            from ..stream.hub import get_stream_hub

            get_stream_hub().publish(
                "state",
                {
                    "time_slot": state.get("time_slot"),
                    "scheduler": state.get("scheduler"),
                    "metrics": state.get("metrics"),
                    "unacked_alerts": state.get("unacked_alerts"),
                },
            )
        except Exception:  # pragma: no cover - streaming must never break a step
            pass
        if not results:
            return
        try:
            from ..store.sessions import get_session_store

            st = get_session_store()
            if st.active_id:
                st.record(
                    "decisions",
                    [
                        {
                            "time_slot": r.time_slot,
                            "scheduler": r.decision.scheduler,
                            "selected_band": r.decision.selected_band,
                            "detected": bool(r.detection.detected),
                            "false_alarm": bool(r.detection.false_alarm),
                            "reward": float(r.reward),
                        }
                        for r in results
                    ],
                )
                m = state.get("metrics", {})
                st.record("metrics", [{"time_slot": state.get("time_slot"), **m}])
        except Exception:  # pragma: no cover
            pass

    # --- durable sessions (Step 7) --------------------------------- #
    def session_start(self, name: str, tags: list) -> dict:
        from ..store.sessions import get_session_store

        return get_session_store().start(
            name,
            list(tags),
            {
                "mode": get_mode_manager().mode,
                "scenario": self._scenario_name or self._preset_name or "",
                "scheduler": self._scheduler_name,
            },
        )

    def session_finish(self) -> dict:
        from ..store.sessions import get_session_store

        store = get_session_store()
        # Capture a final analysis / DF / alert snapshot so the mission report
        # has tracks, fixes and alerts even though only decisions + metrics are
        # streamed per step. Best-effort: never let this break finish().
        if store.active_id:
            try:
                snap = self._analysis_snapshot()
                t = snap.get("t")
                if snap.get("tracks"):
                    store.record(
                        "tracks", [{**tr, "time_slot": t} for tr in snap["tracks"]]
                    )
                from ..alerting.engine import get_alert_store

                alist = [a.model_dump() for a in get_alert_store().list()]
                if alist:
                    store.record("alerts", [{**a, "time_slot": t} for a in alist])
            except Exception:  # pragma: no cover - snapshot is optional
                pass
            try:
                fixes = self._df_snapshot().get("fixes", [])
                if fixes:
                    store.record(
                        "df_fixes",
                        [{**f, "time_slot": self._df_snapshot().get("t")} for f in fixes],
                    )
            except Exception:  # pragma: no cover
                pass

        return store.finish()

    def session_list(self) -> list[dict]:
        from ..store.sessions import get_session_store

        return get_session_store().list()

    def session_meta(self, sid: str) -> dict:
        from ..store.sessions import get_session_store

        return get_session_store().meta(sid)

    def session_data(self, sid: str, kind: str) -> list[dict]:
        from ..store.sessions import get_session_store

        return get_session_store().data(sid, kind)

    def session_export(self, sid: str) -> bytes:
        from ..store.sessions import get_session_store

        return get_session_store().export_zip(sid)

    def session_import(self, blob: bytes) -> dict:
        from ..store.sessions import get_session_store

        return get_session_store().import_zip(blob)

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
            self._publish_and_record(state, results)
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
                        "counterfactual": d.counterfactual,
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
                "preset": self._preset_name,
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

            # Prefer the observed spectrum (== truth on a plain env; jammed /
            # spoofed under simulated EW effects).
            power_src = getattr(env, "power_observed", env.power_db)
            occ_src = getattr(env, "occupancy_observed", env.occupancy)
            synth_src = getattr(env, "is_synthetic_effect", None)

            lo = max(0, t - WATERFALL_SLOTS + 1)
            power_window = power_src[lo : t + 1]
            occ_window = occ_src[lo : t + 1]
            synth_window = (
                synth_src[lo : t + 1] if synth_src is not None else None
            )

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
                "platform": get_mode_manager().snapshot(),
                "live": bool(getattr(sim.env, "live", False)),
                "metrics_applicability": "proxy"
                if getattr(sim.env, "live", False)
                else "ground_truth",
                "protected_bands": sorted(get_tasking_state().protected_bands),
                "protected_override_count": int(getattr(sim, "override_count", 0)),
                "scenario": self._scenario_name,
                "effects": sim.effect_metrics(),
                "unacked_alerts": self.unacked_alert_count(),
                "df": self._df_summary_safe(),
                "online": self.online_status(),
                "running": not sim.done,
                "done": sim.done,
                "time_slot": sim.t,
                "max_slots": env.num_time_slots,
                "scheduler": sim.scheduler_name,
                "available_schedulers": list_schedulers(),
                "dataset_id": self._dataset_id,
                "preset": self._preset_name,
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
                    "power_db": _round_list(power_src[t].tolist(), 2),
                    "active": occ_window[-1].astype(int).tolist()
                    if len(occ_window)
                    else [0] * env.num_bands,
                    "synthetic_effect": synth_window[-1].astype(int).tolist()
                    if synth_window is not None and len(synth_window)
                    else None,
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
                    "synthetic_effect": synth_window.astype(int).tolist()
                    if synth_window is not None
                    else None,
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
