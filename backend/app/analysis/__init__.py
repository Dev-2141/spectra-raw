"""Signal analysis (Extension Step 4).

Turns the observed spectrum into labelled emitter tracks: per-track feature
extraction, a synthetic-trained behaviour classifier, an unsupervised anomaly
flagger, and a periodic-activation forecaster. All synthetic; no real signal
data.
"""

from .features import TrackFeatures, extract_features, runs_from_occupancy
from .tracks import EmitterTrackObj, extract_tracks

__all__ = [
    "TrackFeatures",
    "extract_features",
    "runs_from_occupancy",
    "EmitterTrackObj",
    "extract_tracks",
]
