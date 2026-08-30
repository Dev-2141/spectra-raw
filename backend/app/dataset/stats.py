"""Dataset statistics."""

from __future__ import annotations

import numpy as np

from ..models.core import DatasetStats, Emitter


def compute_stats(
    occupancy: np.ndarray,
    snr_db: np.ndarray,
    threat: np.ndarray,
    emitters: list[Emitter],
) -> DatasetStats:
    occ = occupancy.astype(bool)
    total_cells = occ.size or 1

    active_bands = int(np.count_nonzero(occ.any(axis=0)))
    active_times = int(np.count_nonzero(occ.any(axis=1)))
    occ_pct = float(occ.mean())

    active_snr = snr_db[occ]
    avg_snr = float(active_snr.mean()) if active_snr.size else 0.0

    type_dist: dict[str, int] = {}
    for e in emitters:
        key = e.behavior.value if hasattr(e.behavior, "value") else str(e.behavior)
        type_dist[key] = type_dist.get(key, 0) + 1

    threat_levels = np.array([e.threat for e in emitters], dtype=float)
    threat_dist = {
        "low(<0.3)": int(np.count_nonzero(threat_levels < 0.3)),
        "medium(0.3-0.7)": int(
            np.count_nonzero((threat_levels >= 0.3) & (threat_levels < 0.7))
        ),
        "high(>=0.7)": int(np.count_nonzero(threat_levels >= 0.7)),
    }

    sparsity = float(1.0 - (np.count_nonzero(occ) / total_cells))

    return DatasetStats(
        occupancy_percentage=round(occ_pct, 5),
        active_band_count=active_bands,
        active_time_count=active_times,
        emitter_type_distribution=type_dist,
        average_snr_db=round(avg_snr, 3),
        threat_distribution=threat_dist,
        sparsity_score=round(sparsity, 5),
    )
