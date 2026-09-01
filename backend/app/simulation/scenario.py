"""Scenario store (Extension Step 3).

A :class:`Scenario` bundles an environment config, a receiver config and a list
of simulated EW effects into one portable, editable unit. The six built-in
presets are re-exposed as read-only scenarios; two new ones ("Jammed Spectrum",
"Spoofed Track") demonstrate the EW-effect overlays. User scenarios live as JSON
files under ``<data_dir>/scenarios/<id>.json``.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..config import get_settings
from ..df.nodes import default_layout
from ..models.core import EWEffectSpec, RFEnvironmentConfig, Scenario, ScenarioSaveRequest
from .presets import _PRESETS

_DF_NODES = default_layout(spread_km=45.0, n=4)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _scenarios_dir() -> Path:
    d = get_settings().data_dir / "scenarios"
    d.mkdir(parents=True, exist_ok=True)
    return d


# --------------------------------------------------------------------------- #
# Built-ins
# --------------------------------------------------------------------------- #
def _builtin_scenarios() -> list[Scenario]:
    out: list[Scenario] = []
    for name, p in _PRESETS.items():
        out.append(
            Scenario(
                scenario_id=f"builtin:{name}",
                name=name,
                description=p["description"],
                tags=["builtin", "preset"],
                builtin=True,
                environment=p["environment"].model_copy(deep=True),
                receiver=p["receiver"].model_copy(deep=True),
                effects=[],
                df_nodes=[n.model_copy(deep=True) for n in _DF_NODES],
            )
        )

    hop_env, hop_rx = _PRESETS["Frequency Hopping Challenge"]["environment"], _PRESETS[
        "Frequency Hopping Challenge"
    ]["receiver"]
    out.append(
        Scenario(
            scenario_id="builtin:Jammed Spectrum",
            name="Jammed Spectrum",
            description=(
                "The hopping scenario with a barrage jammer over bands 20-32 and a "
                "spot jammer parked on band 40. Real emitters under the jam lose "
                "SNR; 'detection under effect' shows how each scheduler copes."
            ),
            tags=["builtin", "ew", "jamming"],
            builtin=True,
            environment=hop_env.model_copy(deep=True),
            receiver=hop_rx.model_copy(deep=True),
            effects=[
                EWEffectSpec(
                    kind="barrage_noise",
                    label="barrage 20-32",
                    start_slot=100,
                    stop_slot=900,
                    band_lo=20,
                    band_hi=32,
                    power_db=14.0,
                ),
                EWEffectSpec(
                    kind="spot_jam",
                    label="spot @40",
                    start_slot=0,
                    stop_slot=1000,
                    band_lo=40,
                    band_hi=40,
                    power_db=22.0,
                ),
            ],
        )
    )

    per_env = _PRESETS["Periodic Radar-Like Challenge"]["environment"]
    per_rx = _PRESETS["Periodic Radar-Like Challenge"]["receiver"]
    out.append(
        Scenario(
            scenario_id="builtin:Spoofed Track",
            name="Spoofed Track",
            description=(
                "The periodic scenario plus a repeater ghost (band 12 -> band 30, "
                "3-slot delay) and a fake periodic track on band 8. 'Spoof "
                "deception count' rises when a scheduler chases the decoys."
            ),
            tags=["builtin", "ew", "deception"],
            builtin=True,
            environment=per_env.model_copy(deep=True),
            receiver=per_rx.model_copy(deep=True),
            effects=[
                EWEffectSpec(
                    kind="repeater_ghost",
                    label="ghost 12->30",
                    start_slot=0,
                    stop_slot=1000,
                    source_band=12,
                    target_band=30,
                    delay_slots=3,
                    spoof_snr_db=13.0,
                ),
                EWEffectSpec(
                    kind="spoof_track",
                    label="fake @8",
                    start_slot=50,
                    stop_slot=950,
                    band_lo=8,
                    target_band=8,
                    spoof_period_slots=17,
                    spoof_pulse_slots=2,
                    spoof_snr_db=12.0,
                ),
            ],
        )
    )
    return out


_BUILTINS: dict[str, Scenario] = {s.scenario_id: s for s in _builtin_scenarios()}


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #
class ScenarioStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()

    def _path(self, scenario_id: str) -> Path:
        safe = scenario_id.replace("/", "_").replace("\\", "_")
        return _scenarios_dir() / f"{safe}.json"

    def list(self) -> list[Scenario]:
        out: list[Scenario] = list(_BUILTINS.values())
        for f in sorted(_scenarios_dir().glob("*.json")):
            try:
                out.append(Scenario(**json.loads(f.read_text("utf-8"))))
            except (ValueError, OSError):
                continue
        return out

    def get(self, scenario_id: str) -> Scenario:
        if scenario_id in _BUILTINS:
            return _BUILTINS[scenario_id]
        path = self._path(scenario_id)
        if not path.is_file():
            raise KeyError(f"scenario not found: {scenario_id}")
        return Scenario(**json.loads(path.read_text("utf-8")))

    def save(self, req: ScenarioSaveRequest, scenario_id: str | None = None) -> Scenario:
        with self._lock:
            now = _utc_now()
            if scenario_id and scenario_id in _BUILTINS:
                raise ValueError("built-in scenarios are read-only; duplicate it first")
            sid = scenario_id or f"scn_{uuid.uuid4().hex[:10]}"
            existing_created = now
            if scenario_id:
                p = self._path(scenario_id)
                if p.is_file():
                    try:
                        existing_created = json.loads(p.read_text("utf-8")).get(
                            "created_at", now
                        )
                    except (ValueError, OSError):
                        pass
            scenario = Scenario(
                scenario_id=sid,
                name=req.name,
                description=req.description,
                tags=req.tags,
                builtin=False,
                created_at=existing_created,
                updated_at=now,
                environment=req.environment,
                receiver=req.receiver,
                effects=req.effects,
            )
            self._path(sid).write_text(scenario.model_dump_json(indent=2), "utf-8")
            return scenario

    def duplicate(self, scenario_id: str, new_name: str | None = None) -> Scenario:
        src = self.get(scenario_id)
        req = ScenarioSaveRequest(
            name=new_name or f"{src.name} (copy)",
            description=src.description,
            tags=[t for t in src.tags if t != "builtin"],
            environment=src.environment.model_copy(deep=True),
            receiver=src.receiver.model_copy(deep=True),
            effects=[e.model_copy(deep=True) for e in src.effects],
        )
        return self.save(req)

    def delete(self, scenario_id: str) -> None:
        if scenario_id in _BUILTINS:
            raise ValueError("cannot delete a built-in scenario")
        path = self._path(scenario_id)
        if not path.is_file():
            raise KeyError(f"scenario not found: {scenario_id}")
        path.unlink()


_store: ScenarioStore | None = None


def get_scenario_store() -> ScenarioStore:
    global _store
    if _store is None:
        _store = ScenarioStore()
    return _store
