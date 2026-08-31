"""TDOA / AOA position solvers + covariance -> error ellipse.

Pure NumPy, deterministic. Coordinates are a local 2-D plane in km. Bearings are
degrees clockwise from +y (north).
"""

from __future__ import annotations

import numpy as np

C_KMS = 299_792.458  # speed of light, km/s
_CHI2_95_2DOF = 5.991


def ellipse_from_cov(cov: np.ndarray, conf_scale: float = _CHI2_95_2DOF) -> tuple[float, float, float]:
    """Return ``(semi_major_km, semi_minor_km, theta_deg)`` for a 2x2 covariance."""
    cov = np.asarray(cov, dtype=float)
    if not np.all(np.isfinite(cov)):
        return (float("inf"), float("inf"), 0.0)
    vals, vecs = np.linalg.eigh(0.5 * (cov + cov.T))
    vals = np.clip(vals, 0.0, None)
    order = np.argsort(vals)[::-1]
    vals = vals[order]
    vecs = vecs[:, order]
    a = float(np.sqrt(conf_scale * vals[0]))
    b = float(np.sqrt(conf_scale * vals[1]))
    theta = float(np.degrees(np.arctan2(vecs[1, 0], vecs[0, 0])))
    return a, b, theta


def cep_km_from_cov(cov: np.ndarray) -> float:
    """Circular Error Probable (50%) approximation from a 2x2 covariance."""
    cov = np.asarray(cov, dtype=float)
    if not np.all(np.isfinite(cov)):
        return float("inf")
    sx2, sy2 = float(cov[0, 0]), float(cov[1, 1])
    return float(1.1774 * np.sqrt(0.5 * (sx2 + sy2)))


# --------------------------------------------------------------------------- #
# TDOA
# --------------------------------------------------------------------------- #
def solve_tdoa(
    node_xy: np.ndarray,
    toa_s: np.ndarray,
    timing_sigma_s: np.ndarray,
    *,
    ref: int = 0,
    iters: int = 60,
) -> tuple[np.ndarray, np.ndarray, bool]:
    """Gauss-Newton multilateration from time-of-arrival differences.

    Returns ``(pos_km[2], cov_km2[2,2], solvable)``.
    """
    nodes = np.asarray(node_xy, dtype=float)
    toa = np.asarray(toa_s, dtype=float)
    sig = np.asarray(timing_sigma_s, dtype=float)
    n = nodes.shape[0]
    if n < 3:
        return np.array([np.nan, np.nan]), np.full((2, 2), np.inf), False

    others = [i for i in range(n) if i != ref]
    # measured range differences (km)
    d = (toa[others] - toa[ref]) * C_KMS
    # per-difference range-noise sigma (km): two independent clocks
    rng_sig = np.sqrt(sig[others] ** 2 + sig[ref] ** 2) * C_KMS
    w = 1.0 / np.maximum(rng_sig**2, 1e-12)

    p = nodes.mean(axis=0) + np.array([1e-3, 1e-3])
    ref_xy = nodes[ref]
    for _ in range(iters):
        r_ref = np.linalg.norm(p - ref_xy) + 1e-9
        g_ref = (p - ref_xy) / r_ref
        resid = np.zeros(len(others))
        J = np.zeros((len(others), 2))
        for k, i in enumerate(others):
            r_i = np.linalg.norm(p - nodes[i]) + 1e-9
            g_i = (p - nodes[i]) / r_i
            resid[k] = (r_i - r_ref) - d[k]
            J[k] = g_i - g_ref
        JtW = J.T * w
        H = JtW @ J
        try:
            step = np.linalg.solve(H + 1e-9 * np.eye(2), JtW @ resid)
        except np.linalg.LinAlgError:
            return p, np.full((2, 2), np.inf), False
        p = p - step
        if np.linalg.norm(step) < 1e-9:
            break

    try:
        cov = np.linalg.inv(H + 1e-9 * np.eye(2))
    except np.linalg.LinAlgError:
        cov = np.full((2, 2), np.inf)
    solvable = bool(np.all(np.isfinite(p)) and np.all(np.isfinite(cov)))
    return p, cov, solvable


# --------------------------------------------------------------------------- #
# AOA
# --------------------------------------------------------------------------- #
def solve_aoa(
    node_xy: np.ndarray,
    bearings_deg: np.ndarray,
    bearing_sigma_deg: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, bool]:
    """Weighted least-squares bearing-line intersection.

    Each bearing (deg clockwise from +y) gives a line through its node; the
    emitter is the point minimising weighted perpendicular distance to all
    lines. Parallel bearings -> unsolvable.
    """
    nodes = np.asarray(node_xy, dtype=float)
    br = np.radians(np.asarray(bearings_deg, dtype=float))
    n = nodes.shape[0]
    if n < 2:
        return np.array([np.nan, np.nan]), np.full((2, 2), np.inf), False

    # unit direction of each bearing ray; perpendicular normal n_perp
    ux, uy = np.sin(br), np.cos(br)
    nx, ny = np.cos(br), -np.sin(br)          # perpendicular to (ux, uy)
    # line: n_perp . (p - node) = 0  ->  [nx ny] p = nx*node_x + ny*node_y
    A = np.column_stack([nx, ny])
    rhs = nx * nodes[:, 0] + ny * nodes[:, 1]
    # angular error -> positional sigma grows with range; use a nominal 10 km
    lin_sig = np.maximum(np.radians(bearing_sigma_deg) * 10.0, 1e-3)
    w = 1.0 / lin_sig**2

    AtW = A.T * w
    H = AtW @ A
    if np.linalg.cond(H) > 1e10 or not np.all(np.isfinite(H)):
        return np.array([np.nan, np.nan]), np.full((2, 2), np.inf), False
    try:
        p = np.linalg.solve(H, AtW @ rhs)
        cov = np.linalg.inv(H)
    except np.linalg.LinAlgError:
        return np.array([np.nan, np.nan]), np.full((2, 2), np.inf), False
    return p, cov, bool(np.all(np.isfinite(p)))


# --------------------------------------------------------------------------- #
def fuse_estimates(
    est_a: tuple[np.ndarray, np.ndarray, bool] | None,
    est_b: tuple[np.ndarray, np.ndarray, bool] | None,
) -> tuple[np.ndarray, np.ndarray, bool]:
    """Information-form fusion of two independent (pos, cov, solvable) estimates."""
    good = [e for e in (est_a, est_b) if e is not None and e[2] and np.all(np.isfinite(e[1]))]
    if not good:
        for e in (est_a, est_b):
            if e is not None:
                return e
        return np.array([np.nan, np.nan]), np.full((2, 2), np.inf), False
    if len(good) == 1:
        return good[0]
    (pa, ca, _), (pb, cb, _) = good
    ia, ib = np.linalg.inv(ca), np.linalg.inv(cb)
    cov = np.linalg.inv(ia + ib)
    pos = cov @ (ia @ pa + ib @ pb)
    return pos, cov, True
