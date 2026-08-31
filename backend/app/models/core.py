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
    emitter_specs: Optional[list["EmitterSpec"]] = Field(
        None,
        description=(
            "Explicit parametric emitters (scenario editor). When present the "
            "generator paints these instead of sampling a random behaviour mix."
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


# --------------------------------------------------------------------------- #
# Hardware / live receive-only path (Extension Step 2)
#
# RECEIVE-ONLY. None of these models carry a transmit parameter. A "sweep" is a
# power-vs-frequency snapshot from an SDR (or a recorded file replayed as one).
# --------------------------------------------------------------------------- #
class SourceMode(str, Enum):
    SIMULATION = "simulation"
    FILE_REPLAY = "file_replay"
    RTL_POWER = "rtl_power"
    HACKRF_SWEEP = "hackrf_sweep"
    SOAPYSDR = "soapysdr"


class HardwareConfig(BaseModel):
    """Receive-only sweep configuration for the live path."""

    source_mode: SourceMode = SourceMode.FILE_REPLAY
    start_freq_hz: float = Field(88_000_000.0, gt=0)
    stop_freq_hz: float = Field(108_000_000.0, gt=0)
    bin_hz: float = Field(100_000.0, gt=0)
    sweep_interval_ms: int = Field(250, ge=10, le=10_000)
    gain_db: Optional[float] = Field(None, description="RX gain, adapter-dependent.")
    ppm: Optional[int] = Field(None, description="Frequency correction, ppm.")
    num_bands: int = Field(64, ge=4, le=512, description="Occupancy band grid.")
    recording_id: Optional[str] = Field(
        None, description="Recording to play back when source_mode=file_replay."
    )
    replay_speed: float = Field(1.0, gt=0.0, le=200.0)
    replay_loop: bool = True


class SweepFrame(BaseModel):
    """One power-vs-frequency snapshot (a full sweep)."""

    ts: float = Field(..., description="Unix timestamp (seconds).")
    seq: int = Field(..., description="Monotonic frame counter within a session.")
    f_start_hz: float
    f_stop_hz: float
    bin_hz: float
    power_dbm: list[float]
    source: str


class HardwareDevice(BaseModel):
    id: str
    label: str
    driver: str
    available: bool
    receive_only: bool = True
    note: str = ""


class HardwareStatus(BaseModel):
    source_mode: str
    running: bool
    available: bool
    device_label: Optional[str] = None
    frames_read: int = 0
    last_frame_ts: Optional[float] = None
    frame_rate_hz: float = 0.0
    buffer_len: int = 0
    latest_seq: int = -1
    error: Optional[str] = None
    recording: bool = False
    recording_id: Optional[str] = None
    hardware_mode: str = "receive_only"
    transmit_capability: bool = False
    detail: str = ""


class BandObservation(BaseModel):
    """DSP output for one band in one frame — what a scheduler consumes live."""

    band: int
    active: bool
    power_dbm: float
    noise_floor_dbm: float
    snr_db: float
    confidence: float


class RecordingMeta(BaseModel):
    recording_id: str
    created_at: str
    name: str
    source: str
    device_label: Optional[str] = None
    start_freq_hz: float
    stop_freq_hz: float
    bin_hz: float
    frame_count: int
    duration_s: float
    first_frame_ts: Optional[float] = None
    last_frame_ts: Optional[float] = None


class HardwareStartRequest(BaseModel):
    """Optional inline config for POST /api/hardware/start."""

    config: Optional[HardwareConfig] = None


class RecordStartRequest(BaseModel):
    name: Optional[str] = None


# --------------------------------------------------------------------------- #
# Parametric emitter model (Extension Step 3)
# --------------------------------------------------------------------------- #
class AntennaPattern(BaseModel):
    """Synthetic antenna gain shape (affects observed SNR over time)."""

    kind: str = Field("omni", description="omni | sector | rotating")
    peak_gain_db: float = 0.0
    # sector: main-beam within +/- beamwidth_deg of boresight_deg
    boresight_deg: float = 0.0
    beamwidth_deg: float = 90.0
    backlobe_db: float = -20.0
    # rotating: boresight sweeps 360 deg every rotation_period_slots
    rotation_period_slots: int = 24


class Kinematics(BaseModel):
    """Emitter motion for propagation/Doppler (synthetic 2-D plane, km)."""

    kind: str = Field("static", description="static | waypoint")
    x_km: float = 0.0
    y_km: float = 0.0
    # waypoint: linear travel between (x_km,y_km) and (x2_km,y2_km) over the run
    x2_km: float = 0.0
    y2_km: float = 0.0
    speed_kms: float = 0.0  # informational; travel is fitted to the timeline


class EmitterSpec(BaseModel):
    """A fully specified synthetic emitter for the scenario editor."""

    id: int = 0
    label: str = ""
    home_band: int = 0
    threat: float = Field(0.3, ge=0.0, le=1.0)
    high_priority: bool = False
    snr_db: float = 14.0
    modulation: str = Field("none", description="am|fm|psk|fsk|chirp|noise|none label only")

    # frequency agility
    agility: str = Field("fixed", description="fixed | list_hop | random_hop | sweep")
    hop_bands: list[int] = Field(default_factory=list)
    hop_interval_slots: int = 6
    sweep_span_bands: int = 8

    # on/off model
    duty: str = Field("blocks", description="blocks | periodic | bursts | low_duty")
    period_slots: int = 20
    pulse_slots: int = 2
    phase_slots: int = 0

    # PRI stagger model (radar-like); applies when duty == 'periodic'
    pri_model: str = Field("fixed", description="fixed | jitter | stagger | dwell_switch")
    pri_jitter_slots: int = 1
    pri_stagger: list[int] = Field(default_factory=list)
    pri_dwell_slots: int = 40

    erp_db: float = 0.0
    antenna: AntennaPattern = Field(default_factory=AntennaPattern)
    kinematics: Kinematics = Field(default_factory=Kinematics)


# --------------------------------------------------------------------------- #
# Simulated EW effects (Extension Step 3) — SIMULATION ONLY, never RF
# --------------------------------------------------------------------------- #
class EWEffectSpec(BaseModel):
    """An adversary-transmitter *effect on our observation* — synthetic only.

    Effects change what the receiver sees (observed occupancy / SNR / power /
    noise floor). They never alter ground truth and never touch a device.
    """

    kind: str = Field(
        ...,
        description="barrage_noise | spot_jam | swept_jam | repeater_ghost | spoof_track",
    )
    label: str = ""
    start_slot: int = 0
    stop_slot: int = 10_000
    band_lo: int = 0
    band_hi: int = 0
    power_db: float = 20.0  # excess over noise floor injected into affected cells
    # swept_jam
    sweep_rate_bands_per_slot: float = 0.5
    # repeater_ghost
    source_band: int = 0
    target_band: int = 0
    delay_slots: int = 3
    # spoof_track
    spoof_period_slots: int = 18
    spoof_pulse_slots: int = 2
    spoof_snr_db: float = 12.0


# --------------------------------------------------------------------------- #
# Scenario (Extension Step 3)
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# Direction finding / geolocation (Extension Step 5) — receive-only
# --------------------------------------------------------------------------- #
class ReceiverNode(BaseModel):
    node_id: str = ""
    name: str = ""
    x_km: float = 0.0
    y_km: float = 0.0
    sync_source: str = "gpsdo"          # gpsdo | ptp | none
    sync_quality: float = Field(0.95, ge=0.0, le=1.0)
    timing_error_ns: float = 20.0       # 1-sigma; larger => bigger ellipse
    bearing_error_deg: float = 3.0      # 1-sigma AOA error
    last_seen_slot: int = -1
    healthy: bool = True
    kind: str = "sim"                   # sim | lan


class GeoFix(BaseModel):
    track_id: str
    time_slot: int
    est_x_km: float
    est_y_km: float
    true_x_km: Optional[float] = None   # sim only
    true_y_km: Optional[float] = None
    ellipse_a_km: float = 0.0           # semi-major (95%)
    ellipse_b_km: float = 0.0           # semi-minor (95%)
    ellipse_theta_deg: float = 0.0
    cep_km: float = 0.0
    error_km: Optional[float] = None    # |est - true|, sim only
    n_nodes: int = 0
    method: str = "tdoa+aoa"
    solvable: bool = True


class DFNodesRequest(BaseModel):
    nodes: list[ReceiverNode] = Field(default_factory=list)


class DFRegisterRequest(BaseModel):
    key: str
    node: ReceiverNode


class Scenario(BaseModel):
    """A portable, editable experiment: environment + emitters + effects + rx."""

    scenario_id: str = ""
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    builtin: bool = False
    created_at: str = ""
    updated_at: str = ""
    environment: RFEnvironmentConfig
    receiver: ReceiverConfig = Field(default_factory=ReceiverConfig)
    effects: list[EWEffectSpec] = Field(default_factory=list)
    df_nodes: list[ReceiverNode] = Field(default_factory=list)


class ScenarioSaveRequest(BaseModel):
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    environment: RFEnvironmentConfig
    receiver: ReceiverConfig = Field(default_factory=ReceiverConfig)
    effects: list[EWEffectSpec] = Field(default_factory=list)
    df_nodes: list[ReceiverNode] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Monte Carlo (Extension Step 3)
# --------------------------------------------------------------------------- #
class MonteCarloRequest(BaseModel):
    scenario_id: Optional[str] = None
    environment: Optional[RFEnvironmentConfig] = None
    receiver: Optional[ReceiverConfig] = None
    effects: list[EWEffectSpec] = Field(default_factory=list)
    schedulers: list[str] = Field(
        default_factory=lambda: ["round_robin", "random", "priority", "ucb_bandit"]
    )
    seeds: list[int] = Field(default_factory=list)
    n_seeds: int = Field(12, ge=2, le=200)
    base_seed: int = 20260901
    steps: int = Field(800, ge=50, le=20000)


class MetricAggregate(BaseModel):
    metric: str
    mean: float
    std: float
    ci95_low: float
    ci95_high: float
    n: int


class MonteCarloEntry(BaseModel):
    scheduler: str
    aggregates: list[MetricAggregate]
    win_rate: float  # fraction of seeds this scheduler had the best avg_reward


class MonteCarloReport(BaseModel):
    montecarlo_id: str
    created_at: str
    scenario_id: Optional[str] = None
    scenario_name: str = ""
    schedulers: list[str]
    seeds: list[int]
    steps: int
    number_of_bands: int
    entries: list[MonteCarloEntry]
    ranking: list[str]
    winner: str


# --------------------------------------------------------------------------- #
# Emitter/threat library (Extension Step 4) — synthetic only
# --------------------------------------------------------------------------- #
class EmitterLibraryEntry(BaseModel):
    entry_id: str = ""
    name: str
    synthetic: bool = True  # always
    freq_lo_mhz: float = 0.0
    freq_hi_mhz: float = 0.0
    home_band: int = 0
    behavior: str = "periodic"  # constant|burst|periodic|hopping|low_duty|priority
    modulation: str = "unknown"
    pri_slots: float = 0.0
    pri_jitter: float = 0.0
    hop_span_bands: int = 0
    duty_cycle: float = 0.0
    threat: float = Field(0.3, ge=0.0, le=1.0)
    notes: str = ""
    revision: int = 1
    created_at: str = ""
    updated_at: str = ""


class LibraryEntrySaveRequest(BaseModel):
    name: str
    freq_lo_mhz: float = 0.0
    freq_hi_mhz: float = 0.0
    home_band: int = 0
    behavior: str = "periodic"
    modulation: str = "unknown"
    pri_slots: float = 0.0
    pri_jitter: float = 0.0
    hop_span_bands: int = 0
    duty_cycle: float = 0.0
    threat: float = Field(0.3, ge=0.0, le=1.0)
    notes: str = ""


class LibraryRevision(BaseModel):
    entry_id: str
    revision: int
    action: str  # create | update | delete
    actor: str
    ts: str
    snapshot: dict


# --------------------------------------------------------------------------- #
# Tasking + alerting (Extension Step 4)
# --------------------------------------------------------------------------- #
class WatchList(BaseModel):
    id: str = ""
    name: str
    band_lo: int = 0
    band_hi: int = 0
    weight: float = Field(1.5, ge=0.0, le=10.0)
    enabled: bool = True


class AlertRule(BaseModel):
    id: str = ""
    kind: str  # new_emitter|priority_hit|band_change|hop_detected|anomaly|library_match
    enabled: bool = True
    severity: str = "info"  # info | warn | critical
    threshold: float = 0.6


class Alert(BaseModel):
    alert_id: str
    ts: str
    rule_kind: str
    severity: str
    track_id: Optional[str] = None
    band: Optional[int] = None
    detail: str = ""
    state: str = "open"  # open | ack | closed


class WatchListsRequest(BaseModel):
    watch_lists: list[WatchList] = Field(default_factory=list)


class AlertRulesRequest(BaseModel):
    alert_rules: list[AlertRule] = Field(default_factory=list)


# Resolve the forward reference RFEnvironmentConfig -> EmitterSpec (defined later).
RFEnvironmentConfig.model_rebuild()
