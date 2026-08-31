"""DF engine: turn tracks + nodes + geometry into GeoFixes over time."""

from __future__ import annotations

import numpy as np

from ..models.core import GeoFix
from .fusion import GeoFusion
from .geometry import bearing_deg, emitter_world_positions, match_track_to_emitter, toa_seconds
from .solvers import cep_km_from_cov, ellipse_from_cov, fuse_estimates, solve_aoa, solve_tdoa
from .sync import effective_timing_sigma_s, sync_dashboard


class DFEngine:
    def __init__(self) -> None:
        self._fusion: dict[str, GeoFusion] = {}
        self._gen: int | None = None

    def reset(self, gen: int) -> None:
        self._fusion = {}
        self._gen = gen

    # ------------------------------------------------------------------ #
    def compute(self, env, tracks: list[dict], nodes: list, seed: int, up_to_t: int) -> list[GeoFix]:
        node_xy = np.array([[n.x_km, n.y_km] for n in nodes], dtype=float)
        n_nodes = len(nodes)
        timing_sig = np.array([effective_timing_sigma_s(n) for n in nodes])
        bearing_sig = np.array([float(n.bearing_error_deg) for n in nodes])
        world = emitter_world_positions(env, seed, up_to_t)
        is_live = bool(getattr(env, "live", False))

        fixes: list[GeoFix] = []
        for tr in tracks:
            eid = match_track_to_emitter(tr, env)
            if eid is None or eid not in world:
                continue
            true_xy = np.array(world[eid], dtype=float)

            rng = np.random.default_rng(
                (int(seed) & 0xFFFFFFFF) * 1_000_003
                + hash(tr["track_id"]) % 100_000
                + up_to_t
            )
            toa = np.array(
                [toa_seconds(node_xy[i], true_xy) + rng.normal(0.0, timing_sig[i]) for i in range(n_nodes)]
            )
            brg = np.array(
                [(bearing_deg(node_xy[i], true_xy) + rng.normal(0.0, bearing_sig[i])) % 360.0 for i in range(n_nodes)]
            )

            tdoa = solve_tdoa(node_xy, toa, timing_sig) if n_nodes >= 3 else None
            aoa = solve_aoa(node_xy, brg, bearing_sig) if n_nodes >= 2 else None
            pos, cov, solvable = fuse_estimates(tdoa, aoa)

            fuse = self._fusion.setdefault(tr["track_id"], GeoFusion())
            if solvable and np.all(np.isfinite(pos)):
                est, est_cov = fuse.update(pos, cov, up_to_t)
            else:
                est, est_cov = pos, cov

            a, b, theta = ellipse_from_cov(est_cov) if np.all(np.isfinite(est_cov)) else (float("inf"), float("inf"), 0.0)
            cep = cep_km_from_cov(est_cov)
            err = (
                float(np.linalg.norm(est - true_xy))
                if (not is_live and np.all(np.isfinite(est)))
                else None
            )

            fixes.append(
                GeoFix(
                    track_id=tr["track_id"],
                    time_slot=up_to_t,
                    est_x_km=round(float(est[0]), 4) if np.isfinite(est[0]) else 0.0,
                    est_y_km=round(float(est[1]), 4) if np.isfinite(est[1]) else 0.0,
                    true_x_km=None if is_live else round(float(true_xy[0]), 4),
                    true_y_km=None if is_live else round(float(true_xy[1]), 4),
                    ellipse_a_km=round(a, 4) if np.isfinite(a) else 0.0,
                    ellipse_b_km=round(b, 4) if np.isfinite(b) else 0.0,
                    ellipse_theta_deg=round(theta, 2),
                    cep_km=round(cep, 4) if np.isfinite(cep) else 0.0,
                    error_km=round(err, 4) if err is not None else None,
                    n_nodes=n_nodes,
                    method="tdoa+aoa" if (tdoa and aoa) else ("tdoa" if tdoa else "aoa"),
                    solvable=bool(solvable),
                )
            )
        fixes.sort(key=lambda f: (f.cep_km if np.isfinite(f.cep_km) else 1e9))
        return fixes

    def history(self, track_id: str) -> list[dict]:
        f = self._fusion.get(track_id)
        return list(f.history) if f else []


def df_health(nodes: list, fixes: list[GeoFix]) -> dict:
    errs = [f.error_km for f in fixes if f.error_km is not None]
    ceps = [f.cep_km for f in fixes if np.isfinite(f.cep_km)]
    return {
        "nodes": sync_dashboard(nodes),
        "node_count": len(nodes),
        "healthy_nodes": sum(1 for n in nodes if n.healthy),
        "fix_count": len(fixes),
        "rmse_km": round(float(np.sqrt(np.mean(np.square(errs)))), 4) if errs else None,
        "mean_cep_km": round(float(np.mean(ceps)), 4) if ceps else None,
    }


def df_summary(nodes: list, fixes: list[GeoFix]) -> dict:
    ceps = [f.cep_km for f in fixes if np.isfinite(f.cep_km)]
    return {
        "active": len(nodes) >= 2 and len(fixes) > 0,
        "n_nodes": len(nodes),
        "fixes": len(fixes),
        "mean_cep_km": round(float(np.mean(ceps)), 3) if ceps else None,
    }
