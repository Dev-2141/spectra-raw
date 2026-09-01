"""Forward geometry: true TOA / AOA from node & emitter positions, plus
deterministic world positions for emitters that have none.
"""

from __future__ import annotations

import numpy as np

from ..simulation import propagation as prop
from .solvers import C_KMS


def toa_seconds(node_xy, emitter_xy) -> float:
    return float(np.hypot(emitter_xy[0] - node_xy[0], emitter_xy[1] - node_xy[1]) / C_KMS)


def bearing_deg(node_xy, emitter_xy) -> float:
    """Bearing from node to emitter, degrees clockwise from +y."""
    dx = emitter_xy[0] - node_xy[0]
    dy = emitter_xy[1] - node_xy[1]
    return float(np.degrees(np.arctan2(dx, dy)) % 360.0)


def emitter_world_positions(env, seed: int, t: int) -> dict[int, tuple[float, float]]:
    """Map emitter id -> (x_km, y_km) at slot ``t``.

    Parametric emitters use their kinematics; legacy random emitters get a
    stable pseudo-random placement on a ring so DF works on any scenario.
    """
    out: dict[int, tuple[float, float]] = {}
    T = getattr(env, "num_time_slots", 1000)
    specs = getattr(getattr(env, "config", None), "emitter_specs", None)
    spec_by_id = {}
    if specs:
        for i, s in enumerate(specs):
            spec_by_id[s.id if s.id else i] = s

    for e in getattr(env, "emitters", []):
        eid = int(e.id)
        s = spec_by_id.get(eid)
        if s is not None:
            out[eid] = prop.position_at(t, T, s.kinematics)
            continue
        rng = np.random.default_rng(int(seed) * 100_003 + eid * 7919 + 11)
        ang = float(rng.uniform(0.0, 2.0 * np.pi))
        r = float(rng.uniform(8.0, 55.0))
        out[eid] = (r * np.cos(ang), r * np.sin(ang))
    return out


def match_track_to_emitter(track: dict, env) -> int | None:
    """Best-guess emitter id for a track, by band proximity."""
    emitters = getattr(env, "emitters", [])
    if not emitters:
        return None
    bands = set(track.get("bands", [])) or {track.get("primary_band", 0)}
    best_id, best_d = None, 1e9
    for e in emitters:
        hb = int(e.home_band)
        if hb in bands:
            return int(e.id)
        d = min(abs(hb - b) for b in bands)
        if d < best_d:
            best_d, best_id = d, int(e.id)
    return best_id if best_d <= 8 else None
