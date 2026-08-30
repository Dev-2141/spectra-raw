"""DeepSense-style synthetic dataset generation, storage, and replay."""

from .generator import BEHAVIOR_LABELS, build_dataset
from .stats import compute_stats
from .store import DatasetStore, get_store

__all__ = [
    "BEHAVIOR_LABELS",
    "build_dataset",
    "compute_stats",
    "DatasetStore",
    "get_store",
]
