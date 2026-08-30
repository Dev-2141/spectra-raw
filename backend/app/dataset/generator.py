"""Synthetic DeepSense-style dataset generator.

Wraps :class:`RFEnvironment` (the same seeded generator the live simulation
uses) and extracts the time-frequency arrays plus per-cell emitter-type labels
that a supervised spectrum-sensing pipeline would train on.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from ..models.core import DatasetMeta, EmitterBehavior, RFEnvironmentConfig
from ..simulation.environment import RFEnvironment
from .stats import compute_stats

# Stable integer codes for the emitter-type label matrix (-1 = inactive cell).
BEHAVIOR_LABELS: dict[str, int] = {
    b.value: i for i, b in enumerate(EmitterBehavior)
}


def _label_matrix(env: RFEnvironment) -> np.ndarray:
    """Per-(time, band) emitter-behavior code; -1 where nothing is transmitting."""
    labels = np.full(env.occupancy.shape, -1, dtype=np.int16)
    active_t, active_b = np.nonzero(env.occupancy)
    for t, b in zip(active_t, active_b):
        eid = int(env.emitter_id_matrix[t, b])
        if 0 <= eid < len(env.emitters):
            labels[t, b] = BEHAVIOR_LABELS[env.emitters[eid].behavior.value]
    return labels


def build_dataset(
    config: RFEnvironmentConfig, name: str | None = None
) -> tuple[DatasetMeta, dict[str, np.ndarray]]:
    """Return ``(meta, arrays)`` for a fresh synthetic dataset.

    ``arrays`` keys: occupancy, power_db, snr_db, threat, labels, emitter_id.
    """
    env = RFEnvironment(config)
    labels = _label_matrix(env)

    arrays = {
        "occupancy": env.occupancy.astype(np.int8),
        "power_db": env.power_db.astype(np.float32),
        "snr_db": env.snr_db.astype(np.float32),
        "threat": env.threat.astype(np.float32),
        "labels": labels,
        "emitter_id": env.emitter_id_matrix.astype(np.int32),
    }

    stats = compute_stats(env.occupancy, env.snr_db, env.threat, env.emitters)
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    dataset_id = f"ds_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{config.seed}"

    meta = DatasetMeta(
        dataset_id=dataset_id,
        created_at=created,
        name=name or f"synthetic-{config.num_bands}b-{config.num_time_slots}t-seed{config.seed}",
        number_of_bands=config.num_bands,
        number_of_time_slots=config.num_time_slots,
        config=config,
        emitters=env.emitters,
        stats=stats,
        files={},  # filled in by the store on save
        labels=BEHAVIOR_LABELS,
    )
    return meta, arrays
