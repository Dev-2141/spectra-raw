"""Unsupervised spectrum anomaly flagging (Extension Step 4).

Learns a per-band baseline (mean/std power, mean occupancy) over an early
window, then flags later cells that deviate: a power spike beyond ``k`` sigma,
or activity on a band that was essentially idle during the baseline.
"""

from __future__ import annotations

import numpy as np

_K_SIGMA = 4.0
_MIN_LEARN = 60


def detect(env, up_to_t: int, learn_slots: int | None = None, k: float = _K_SIGMA) -> dict:
    power = getattr(env, "power_observed", getattr(env, "power_db"))
    occ = getattr(env, "occupancy_observed", getattr(env, "occupancy"))
    T = min(up_to_t + 1, power.shape[0])
    B = power.shape[1]

    learn = learn_slots or max(_MIN_LEARN, T // 4)
    learn = min(learn, max(1, T - 1))
    if T <= learn + 2:
        return {"baseline_slots": learn, "ready": False, "flags": [], "anomalous_bands": []}

    base_p = power[:learn]
    base_o = occ[:learn].astype(float)
    mean = base_p.mean(axis=0)
    std = np.maximum(base_p.std(axis=0), 1.0)
    base_occ_rate = base_o.mean(axis=0)

    flags: list[dict] = []
    window = slice(learn, T)
    p_win = power[window]
    o_win = occ[window].astype(bool)

    z = (p_win - mean) / std
    spike_idx = np.argwhere(z > k)
    for ti, b in spike_idx[:400]:
        flags.append(
            {
                "time_slot": int(learn + ti),
                "band": int(b),
                "kind": "power_spike",
                "z": round(float(z[ti, b]), 2),
            }
        )

    quiet_bands = np.where(base_occ_rate < 0.02)[0]
    for b in quiet_bands:
        active_slots = np.where(o_win[:, b])[0]
        if active_slots.size >= 3:
            flags.append(
                {
                    "time_slot": int(learn + active_slots[0]),
                    "band": int(b),
                    "kind": "new_activity",
                    "z": round(float(active_slots.size), 1),
                }
            )

    anomalous_bands = sorted({f["band"] for f in flags})
    flags.sort(key=lambda f: (-f["z"], f["time_slot"]))
    return {
        "baseline_slots": learn,
        "ready": True,
        "flags": flags[:200],
        "anomalous_bands": anomalous_bands,
    }
