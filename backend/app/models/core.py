"""Core data models for the SPECTRA-SCAN AI simulation.

All models describe a *synthetic* electronic-support (ES) scanning problem:
a receive-only sensor with limited instantaneous bandwidth trying to intercept
transmissions in a wide simulated spectrum. Nothing here transmits.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class EmitterBehavior(str, Enum):
    """Synthetic emitter activity patterns."""

    CONSTANT = "constant"
    BURST = "burst"
    PERIODIC = "periodic"
    HOPPING = "hopping"
    LOW_DUTY = "low_duty"
    PRIORITY = "priority"


# --------------------------------------------------------------------------- #
# Environment
# --------------------------------------------------------------------------- #
class Band(BaseModel):
    """A single frequency band (channel) in the divided spectrum."""

    index: int = Field(..., description="Band index, 0-based.")
    center_mhz: float = Field(..., description="Synthetic center frequency in MHz.")
    width_mhz: float = Field(..., description="Synthetic channel width in MHz.")


class Emitter(BaseModel):
    """Metadata describing one synthetic emitter."""

    id: int
    label: str
    behavior: EmitterBehavior
    home_band: int = Field(..., description="Primary band index (hopping emitters roam).")
    threat: float = Field(..., ge=0.0, le=1.0, description="Synthetic threat/value score.")
    high_priority: bool = False
    snr_db: float = Field(..., description="Nominal peak SNR in dB when active.")
    duty_cycle: float = Field(..., ge=0.0, le=1.0, description="Fraction of time active.")
    params: dict = Field(default_factory=dict, description="Behavior-specific parameters.")


class RFEnvironmentConfig(BaseModel):
    """Configuration for the synthetic RF environment generator."""

    num_bands: int = Field(64, ge=4, le=512)
    num_time_slots: int = Field(1000, ge=10, le=20000)
    emitter_density: float = Field(
        0.15, ge=0.0, le=1.0, description="Emitters per band (approx)."
    )
    noise_floor_db: float = Field(-100.0, description="Noise floor in dBm (synthetic).")
    snr_min_db: float = Field(4.0, description="Minimum active-emitter SNR in dB.")
    snr_max_db: float = Field(22.0, description="Maximum active-emitter SNR in dB.")
    base_center_mhz: float = Field(2400.0, description="Synthetic band-plan start (MHz).")
    band_width_mhz: float = Field(5.0, description="Synthetic per-band width (MHz).")
    high_priority_fraction: float = Field(
        0.15, ge=0.0, le=1.0, description="Fraction of emitters flagged high priority."
    )
    behavior_weights: Optional[dict[str, float]] = Field(
        None,
        description=(
            "Optional emitter-behavior sampling weights, e.g. "
            '{"hopping": 0.6, "burst": 0.2, "priority": 0.2}. Missing behaviors '
            "get weight 0. Falls back to the built-in mix when omitted."
        ),
    )
    seed: int = Field(1234, description="Master RNG seed for reproducibility.")


class RFEnvironmentState(BaseModel):
    """Lightweight snapshot of the environment for the API."""

    num_bands: int
    num_time_slots: int
    noise_floor_db: float
    time_slot: int
    emitters: list[Emitter]
    bands: list[Band]


# --------------------------------------------------------------------------- #
# Receiver digital twin
# --------------------------------------------------------------------------- #
class ReceiverConfig(BaseModel):
    """Configuration for the receive-only sensor digital twin."""

    dwell_slots: int = Field(1, ge=1, le=50, description="Time slots spent per visit.")
    retune_delay_slots: int = Field(
        1, ge=0, le=20, description="Dead slots incurred when the band changes."
    )
    detection_threshold_db: float = Field(
        6.0, description="Measured SNR (dB) required for a nominal detection."
    )
    snr_measurement_noise_db: float = Field(
        2.0, ge=0.0, description="Std-dev of the SNR estimate error in dB."
    )
    false_alarm_prob: float = Field(
        0.02, ge=0.0, le=1.0, description="P(false alarm) on an inactive scan."
    )
    scan_window: int = Field(
        1, ge=1, le=16, description="Contiguous bands observed per scan (>=1)."
    )


class ReceiverState(BaseModel):
    """Mutable state of the receiver digital twin."""

    current_band: int = 0
    retune_cooldown: int = 0
    visited_bands: list[int] = Field(default_factory=list)
    detections: list[int] = Field(default_factory=list)
    total_scans: int = 0


# --------------------------------------------------------------------------- #
# Decisions, events, results
# --------------------------------------------------------------------------- #
class ScanDecision(BaseModel):
    """A scheduler's choice for the next scan, with explainability payload."""

    time_slot: int
    selected_band: int
    scheduler: str
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    predicted_active: Optional[bool] = Field(
        None, description="Scheduler's prediction of band activity, if it makes one."
    )
    reasons: list[str] = Field(default_factory=list, description="Top factors (<=3).")
    alternatives: list[int] = Field(
        default_factory=list, description="Runner-up candidate bands."
    )
    explanation: str = ""


class DetectionEvent(BaseModel):
    """Outcome of observing a band at a given time slot."""

    time_slot: int
    band: int
    true_active: bool
    detected: bool
    false_alarm: bool
    measured_snr_db: float
    measured_power_db: float
    threat: float


class SchedulerMetrics(BaseModel):
    """Aggregated performance metrics for a run."""

    steps: int = 0
    total_reward: float = 0.0
    average_reward: float = 0.0

    hits: int = 0
    misses: int = 0
    false_alarms: int = 0
    empty_scans: int = 0

    probability_of_detection: float = 0.0
    false_alarm_rate: float = 0.0
    interception_ratio: float = 0.0
    average_intercept_delay: float = 0.0
    high_priority_detection_rate: float = 0.0
    missed_opportunity_count: int = 0
    scan_coverage: float = 0.0
    average_revisit_time: float = 0.0
    correct_prediction_percentage: float = 0.0

    emitter_events_total: int = 0
    emitter_events_detected: int = 0


class SimulationStepResult(BaseModel):
    """Everything produced by advancing the simulation one dwell."""

    time_slot: int
    decision: ScanDecision
    detection: DetectionEvent
    reward: float
    reward_breakdown: dict
    retuned: bool
    done: bool
    metrics: SchedulerMetrics


# --------------------------------------------------------------------------- #
# API request bodies
# --------------------------------------------------------------------------- #
class ResetRequest(BaseModel):
    """Body for POST /api/simulation/reset."""

    preset: Optional[str] = Field(
        None, description="Load a named scenario preset as the base config."
    )
    environment: Optional[RFEnvironmentConfig] = None
    receiver: Optional[ReceiverConfig] = None
    scheduler: str = "round_robin"
    scheduler_params: dict = Field(default_factory=dict)


class StepRequest(BaseModel):
    """Body for POST /api/simulation/step."""

    count: int = Field(1, ge=1, le=2000)


class RunRequest(BaseModel):
    """Body for POST /api/simulation/run."""

    steps: int = Field(500, ge=1, le=20000)
    scheduler: Optional[str] = None
    scheduler_params: dict = Field(default_factory=dict)
    reset: bool = Field(
        True, description="Reset the run before executing (keeps current config)."
    )


class TrainRequest(BaseModel):
    """Body for POST /api/simulation/train (multi-episode learning)."""

    scheduler: str = "q_learning"
    episodes: int = Field(10, ge=1, le=200)
    steps_per_episode: int = Field(500, ge=10, le=20000)
    scheduler_params: dict = Field(default_factory=dict)
    vary_seed: bool = Field(
        True, description="Use a different environment seed per episode."
    )


class EpisodeResult(BaseModel):
    """One training episode summary."""

    episode: int
    seed: int
    steps: int
    total_reward: float
    average_reward: float
    probability_of_detection: float
    interception_ratio: float
    high_priority_detection_rate: float
    missed_opportunity_count: int
    epsilon: Optional[float] = None
    q_states: Optional[int] = None
    q_updates: Optional[int] = None


class TrainingReport(BaseModel):
    """Body returned by POST /api/simulation/train."""

    scheduler: str
    episodes: int
    steps_per_episode: int
    episode_results: list[EpisodeResult]
    first_episode_avg_reward: float
    last_episode_avg_reward: float
    reward_improvement: float
    best_episode: int


# --------------------------------------------------------------------------- #
# Dataset lab (Step 3)
# --------------------------------------------------------------------------- #
class DatasetStats(BaseModel):
    """Summary statistics for a generated dataset."""

    occupancy_percentage: float
    active_band_count: int
    active_time_count: int
    emitter_type_distribution: dict[str, int]
    average_snr_db: float
    threat_distribution: dict[str, int]
    sparsity_score: float


class DatasetMeta(BaseModel):
    """DeepSense-style synthetic dataset descriptor (JSON metadata sidecar)."""

    dataset_id: str
    created_at: str
    name: str
    number_of_bands: int
    number_of_time_slots: int
    config: RFEnvironmentConfig
    emitters: list[Emitter]
    stats: DatasetStats
    files: dict[str, str]
    labels: dict[str, int] = Field(
        default_factory=dict,
        description="Emitter-behavior label -> integer code used in labels matrix.",
    )


class DatasetGenerateRequest(BaseModel):
    """Body for POST /api/dataset/generate."""

    name: Optional[str] = None
    preset: Optional[str] = Field(
        None, description="Generate from a named scenario preset's environment."
    )
    config: Optional[RFEnvironmentConfig] = None


class DatasetLoadRequest(BaseModel):
    """Body for POST /api/dataset/{id}/load."""

    receiver: Optional[ReceiverConfig] = None
    scheduler: str = "round_robin"
    scheduler_params: dict = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Strategy comparison (Step 3)
# --------------------------------------------------------------------------- #
class ComparisonRequest(BaseModel):
    """Body for POST /api/comparison/run."""

    schedulers: list[str] = Field(
        default_factory=lambda: [
            "round_robin",
            "random",
            "priority",
            "epsilon_bandit",
            "ucb_bandit",
            "q_learning",
        ]
    )
    steps: int = Field(1000, ge=10, le=20000)
    seed: Optional[int] = Field(None, description="Override the shared scenario seed.")
    scheduler_params: dict[str, dict] = Field(default_factory=dict)
    series_points: int = Field(60, ge=5, le=400)


class ComparisonSeries(BaseModel):
    time_slot: list[int]
    average_reward: list[float]
    detection_rate: list[float]
    interception_ratio: list[float]
    scan_coverage: list[float]


class ComparisonEntry(BaseModel):
    scheduler: str
    metrics: SchedulerMetrics
    series: ComparisonSeries
    weighted_score: float
    rank: int


class ComparisonReport(BaseModel):
    """Body returned by POST /api/comparison/run."""

    scenario_seed: int
    replayed_dataset: Optional[str] = None
    number_of_bands: int
    number_of_time_slots: int
    steps: int
    schedulers: list[str]
    entries: list[ComparisonEntry]
    metrics_table: list[dict]
    winner: str
    ranking: list[str]
    score_weights: dict[str, float]
