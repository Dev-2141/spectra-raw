// Typed API client for the SPECTRA-SCAN AI backend.
// Vite proxies /api -> http://127.0.0.1:8000 in dev (see vite.config.ts).

const BASE = import.meta.env.VITE_API_BASE ?? "";

// --- auth token plumbing --------------------------------------------------- //
let _token: string | null = null;
let _onUnauthorized: (() => void) | null = null;

export function setAuthToken(token: string | null): void {
  _token = token;
}

export function setUnauthorizedHandler(fn: (() => void) | null): void {
  _onUnauthorized = fn;
}

function authHeaders(extra?: Record<string, string>): Record<string, string> {
  const h: Record<string, string> = { ...(extra ?? {}) };
  if (_token) h["Authorization"] = `Bearer ${_token}`;
  return h;
}

async function guard(res: Response, path: string): Promise<void> {
  if (res.ok) return;
  if (res.status === 401) _onUnauthorized?.();
  throw new Error(`${path} -> ${res.status} ${await res.text()}`);
}

async function jget<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { headers: authHeaders() });
  await guard(res, path);
  return res.json() as Promise<T>;
}

async function jpost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body ?? {}),
  });
  await guard(res, path);
  return res.json() as Promise<T>;
}

async function jput<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "PUT",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body ?? {}),
  });
  await guard(res, path);
  return res.json() as Promise<T>;
}

async function jdelete<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  await guard(res, path);
  return res.json() as Promise<T>;
}

// --------------------------------------------------------------------------- //
export interface Health {
  status: string;
  mode: string;
  transmit_capability: boolean;
  hardware_mode?: string;
  platform_mode?: "simulation" | "live_es";
  auth?: string;
  version?: string;
}

export type Role = "viewer" | "analyst" | "operator" | "admin";
export const ROLE_RANK: Record<Role, number> = {
  viewer: 0,
  analyst: 1,
  operator: 2,
  admin: 3,
};

export interface TokenResponse {
  access_token: string;
  token_type: string;
  username: string;
  role: Role;
  demo: boolean;
  must_change_password: boolean;
  expires_in: number;
}

export interface MeResponse {
  username: string;
  role: Role;
  demo: boolean;
  must_change_password: boolean;
}

export interface PlatformMode {
  mode: "simulation" | "live_es";
  degraded: boolean;
  since: string;
  hardware_mode: string;
  transmit_capability: boolean;
}

export interface AuditEntry {
  id: number;
  ts: string;
  actor: string;
  role: string | null;
  action: string;
  target: string | null;
  detail: unknown;
  mode: string | null;
}

export interface PlatformUser {
  username: string;
  role: Role;
  must_change_password: number;
  created_at: string;
  updated_at: string;
}

// --- hardware / live path (Step 2) -------------------------------------- //
export type SourceMode =
  | "simulation"
  | "file_replay"
  | "rtl_power"
  | "hackrf_sweep"
  | "soapysdr";

export interface HardwareConfig {
  source_mode: SourceMode;
  start_freq_hz: number;
  stop_freq_hz: number;
  bin_hz: number;
  sweep_interval_ms: number;
  gain_db?: number | null;
  ppm?: number | null;
  num_bands: number;
  recording_id?: string | null;
  replay_speed: number;
  replay_loop: boolean;
}

export interface HardwareStatus {
  source_mode: string;
  running: boolean;
  available: boolean;
  device_label?: string | null;
  frames_read: number;
  last_frame_ts?: number | null;
  frame_rate_hz: number;
  buffer_len: number;
  latest_seq: number;
  error?: string | null;
  recording: boolean;
  recording_id?: string | null;
  hardware_mode: string;
  transmit_capability: boolean;
  detail: string;
}

export interface HardwareDeviceInfo {
  id: string;
  label: string;
  driver: string;
  available: boolean;
  receive_only: boolean;
  note: string;
}

export interface RecordingMeta {
  recording_id: string;
  created_at: string;
  name: string;
  source: string;
  device_label?: string | null;
  start_freq_hz: number;
  stop_freq_hz: number;
  bin_hz: number;
  frame_count: number;
  duration_s: number;
}

export interface BandObservation {
  band: number;
  active: boolean;
  power_dbm: number;
  noise_floor_dbm: number;
  snr_db: number;
  confidence: number;
}

export interface SweepFrameDto {
  ts: number;
  seq: number;
  f_start_hz: number;
  f_stop_hz: number;
  bin_hz: number;
  power_dbm: number[];
  source: string;
}

// --- scenarios & simulated EW effects (Step 3) ------------------------- //
export interface EWEffectSpec {
  kind:
    | "barrage_noise"
    | "spot_jam"
    | "swept_jam"
    | "repeater_ghost"
    | "spoof_track";
  label: string;
  start_slot: number;
  stop_slot: number;
  band_lo: number;
  band_hi: number;
  power_db: number;
  sweep_rate_bands_per_slot: number;
  source_band: number;
  target_band: number;
  delay_slots: number;
  spoof_period_slots: number;
  spoof_pulse_slots: number;
  spoof_snr_db: number;
}

export interface Scenario {
  scenario_id: string;
  name: string;
  description: string;
  tags: string[];
  builtin: boolean;
  created_at: string;
  updated_at: string;
  environment: EnvironmentConfig & {
    high_priority_fraction?: number;
    behavior_weights?: Record<string, number> | null;
  };
  receiver: ReceiverConfig;
  effects: EWEffectSpec[];
}

export interface ScenarioSaveBody {
  name: string;
  description?: string;
  tags?: string[];
  environment: Scenario["environment"];
  receiver: ReceiverConfig;
  effects: EWEffectSpec[];
}

export interface EffectMetrics {
  has_effects: boolean;
  effect_labels?: Array<{
    kind: string;
    label: string;
    start_slot: number;
    stop_slot: number;
    band_lo: number;
    band_hi: number;
  }>;
  synthetic_scans?: number;
  detection_under_effect_rate?: number | null;
  detection_under_effect_n?: number;
  spoof_deception_count?: number;
}

export interface MetricAggregate {
  metric: string;
  mean: number;
  std: number;
  ci95_low: number;
  ci95_high: number;
  n: number;
}

export interface MonteCarloEntry {
  scheduler: string;
  aggregates: MetricAggregate[];
  win_rate: number;
}

export interface MonteCarloReport {
  montecarlo_id: string;
  created_at: string;
  scenario_id: string | null;
  scenario_name: string;
  schedulers: string[];
  seeds: number[];
  steps: number;
  number_of_bands: number;
  entries: MonteCarloEntry[];
  ranking: string[];
  winner: string;
}

// --- signal analysis, library, tasking, alerts (Step 4) --------------- //
export interface EmitterTrack {
  track_id: string;
  first_seen: number;
  last_seen: number;
  age_slots: number;
  idle_slots: number;
  bands: number[];
  primary_band: number;
  run_count: number;
  active_slots: number;
  threat: number;
  high_priority: boolean;
  is_synthetic_effect: boolean;
  freq_behavior: string;
  spectral_shape: string;
  class: string;
  class_confidence: number;
  class_probabilities: Record<string, number>;
  modulation: string;
  pri_estimate: number;
  pri_jitter: number;
  duty_cycle: number;
  snr_mean_db: number;
  features: Record<string, number | string>;
  library_matches: Array<{
    entry_id: string;
    name: string;
    behavior: string;
    modulation: string;
    threat: number;
    score: number;
  }>;
}

export interface AnomalyReport {
  baseline_slots: number;
  ready: boolean;
  flags: Array<{ time_slot: number; band: number; kind: string; z: number }>;
  anomalous_bands: number[];
}

export interface ForecastReport {
  time_slot: number;
  forecast: Array<{
    track_id: string;
    band: number;
    pri_slots: number;
    pri_jitter: number;
    next_slots: number[];
    slots_until_next: number;
    confidence: number;
  }>;
}

export interface LibraryEntry {
  entry_id: string;
  name: string;
  synthetic: boolean;
  freq_lo_mhz: number;
  freq_hi_mhz: number;
  home_band: number;
  behavior: string;
  modulation: string;
  pri_slots: number;
  pri_jitter: number;
  hop_span_bands: number;
  duty_cycle: number;
  threat: number;
  notes: string;
  revision: number;
  created_at: string;
  updated_at: string;
}

export interface LibraryEntryBody {
  name: string;
  freq_lo_mhz?: number;
  freq_hi_mhz?: number;
  home_band?: number;
  behavior: string;
  modulation?: string;
  pri_slots?: number;
  pri_jitter?: number;
  hop_span_bands?: number;
  duty_cycle?: number;
  threat: number;
  notes?: string;
}

export interface LibraryRevisionRow {
  entry_id: string;
  revision: number;
  action: string;
  actor: string;
  ts: string;
  snapshot: Record<string, unknown>;
}

export interface WatchListItem {
  id: string;
  name: string;
  band_lo: number;
  band_hi: number;
  weight: number;
  enabled: boolean;
}

export interface AlertRuleItem {
  id: string;
  kind: string;
  enabled: boolean;
  severity: string;
  threshold: number;
}

export interface AlertItem {
  alert_id: string;
  ts: string;
  rule_kind: string;
  severity: string;
  track_id: string | null;
  band: number | null;
  detail: string;
  state: "open" | "ack" | "closed";
}

// --- direction finding / geolocation (Step 5) ------------------------- //
export interface ReceiverNode {
  node_id: string;
  name: string;
  x_km: number;
  y_km: number;
  sync_source: string;
  sync_quality: number;
  timing_error_ns: number;
  bearing_error_deg: number;
  last_seen_slot: number;
  healthy: boolean;
  kind: string;
}

export interface GeoFix {
  track_id: string;
  time_slot: number;
  est_x_km: number;
  est_y_km: number;
  true_x_km: number | null;
  true_y_km: number | null;
  ellipse_a_km: number;
  ellipse_b_km: number;
  ellipse_theta_deg: number;
  cep_km: number;
  error_km: number | null;
  n_nodes: number;
  method: string;
  solvable: boolean;
}

export interface DFHealth {
  nodes: Array<{
    node_id: string;
    name: string;
    sync_source: string;
    sync_quality: number;
    timing_sigma_ns: number;
    bearing_error_deg: number;
    healthy: boolean;
    last_seen_slot: number;
    kind: string;
    x_km: number;
    y_km: number;
  }>;
  node_count: number;
  healthy_nodes: number;
  fix_count: number;
  rmse_km: number | null;
  mean_cep_km: number | null;
}

export interface DFSummary {
  active: boolean;
  n_nodes: number;
  fixes: number;
  mean_cep_km: number | null;
}

export interface Metrics {
  steps: number;
  total_reward: number;
  average_reward: number;
  hits: number;
  misses: number;
  false_alarms: number;
  empty_scans: number;
  probability_of_detection: number;
  false_alarm_rate: number;
  interception_ratio: number;
  average_intercept_delay: number;
  high_priority_detection_rate: number;
  missed_opportunity_count: number;
  scan_coverage: number;
  average_revisit_time: number;
  correct_prediction_percentage: number;
  emitter_events_total: number;
  emitter_events_detected: number;
}

export interface Emitter {
  id: number;
  label: string;
  behavior: string;
  home_band: number;
  threat: number;
  high_priority: boolean;
  snr_db: number;
  duty_cycle: number;
}

export interface EnvironmentConfig {
  num_bands: number;
  num_time_slots: number;
  emitter_density: number;
  noise_floor_db: number;
  snr_min_db: number;
  snr_max_db: number;
  seed: number;
}

export interface ReceiverConfig {
  dwell_slots: number;
  retune_delay_slots: number;
  detection_threshold_db: number;
  false_alarm_prob: number;
  scan_window: number;
}

export interface DecisionPayload {
  selected_band: number;
  scheduler: string;
  confidence: number;
  predicted_active: boolean | null;
  reasons: string[];
  alternatives: number[];
  explanation: string;
}

export interface StepResult {
  time_slot: number;
  reward: number;
  reward_breakdown: Record<string, number>;
  retuned: boolean;
  decision: DecisionPayload;
  detection: {
    band: number;
    true_active: boolean;
    detected: boolean;
    false_alarm: boolean;
    measured_snr_db: number;
    threat: number;
  };
  metrics: Metrics;
}

export interface ScanPathRow {
  time_slot: number;
  band: number;
  scanned_band: number;
  detected: boolean;
  false_alarm: boolean;
  true_active: boolean;
  reward: number;
}

export interface SimState {
  product: string;
  mode: string;
  platform?: PlatformMode;
  protected_bands?: number[];
  protected_override_count?: number;
  running: boolean;
  done: boolean;
  time_slot: number;
  max_slots: number;
  scheduler: string;
  available_schedulers: string[];
  dataset_id: string | null;
  preset: string | null;
  scenario?: string | null;
  effects?: EffectMetrics;
  unacked_alerts?: number;
  df?: DFSummary;
  replay_mode: boolean;
  environment: {
    num_bands: number;
    num_time_slots: number;
    noise_floor_db: number;
    seed: number;
    emitter_density: number;
    occupancy_percentage: number;
    emitter_count: number;
  };
  receiver: {
    current_band: number;
    dwell_slots: number;
    retune_delay_slots: number;
    detection_threshold_db: number;
    scan_window: number;
    total_scans: number;
  };
  emitters: Emitter[];
  spectrum: {
    time_slot: number;
    power_db: number[];
    active: number[];
    synthetic_effect?: number[] | null;
    threshold_db: number;
    threat_prior: number[];
    predicted_activity: number[];
  };
  waterfall: {
    start_slot: number;
    power_db: number[][];
    active: number[][];
    synthetic_effect?: number[][] | null;
  };
  scan_path: ScanPathRow[];
  reward_series: Array<{ time_slot: number; reward: number }>;
  metrics: Metrics;
  last_step?: StepResult | null;
  steps_executed?: number;
}

export interface DatasetMeta {
  dataset_id: string;
  created_at: string;
  name: string;
  number_of_bands: number;
  number_of_time_slots: number;
  config: EnvironmentConfig;
  emitters: Emitter[];
  stats: DatasetStats;
  labels: Record<string, number>;
}

export interface DatasetStats {
  occupancy_percentage: number;
  active_band_count: number;
  active_time_count: number;
  emitter_type_distribution: Record<string, number>;
  average_snr_db: number;
  threat_distribution: Record<string, number>;
  sparsity_score: number;
}

export interface ComparisonEntry {
  scheduler: string;
  metrics: Metrics;
  weighted_score: number;
  rank: number;
  series: {
    time_slot: number[];
    average_reward: number[];
    detection_rate: number[];
    interception_ratio: number[];
    scan_coverage: number[];
  };
}

export interface ComparisonReport {
  scenario_seed: number;
  replayed_dataset: string | null;
  number_of_bands: number;
  number_of_time_slots: number;
  steps: number;
  schedulers: string[];
  entries: ComparisonEntry[];
  metrics_table: Array<Record<string, number | string>>;
  winner: string;
  ranking: string[];
  score_weights: Record<string, number>;
}

export interface EpisodeResult {
  episode: number;
  seed: number;
  steps: number;
  total_reward: number;
  average_reward: number;
  probability_of_detection: number;
  interception_ratio: number;
  high_priority_detection_rate: number;
  missed_opportunity_count: number;
  epsilon: number | null;
  q_states: number | null;
  q_updates: number | null;
}

export interface TrainingReport {
  scheduler: string;
  episodes: number;
  steps_per_episode: number;
  episode_results: EpisodeResult[];
  first_episode_avg_reward: number;
  last_episode_avg_reward: number;
  reward_improvement: number;
  best_episode: number;
}

export interface ExplainRow {
  time_slot: number;
  scheduler: string;
  selected_band: number;
  confidence: number;
  predicted_active: boolean | null;
  reward: number;
  outcome: "hit" | "miss" | "false_alarm" | "empty";
  reasons: string[];
  alternatives: number[];
  explanation: string;
  reward_breakdown: Record<string, number>;
}

export interface RunReport {
  generated_at: string;
  scheduler: string;
  dataset_id: string | null;
  preset: string | null;
  replay_mode: boolean;
  environment_config: EnvironmentConfig;
  receiver_config: ReceiverConfig;
  time_slot: number;
  max_slots: number;
  steps_run: number;
  metrics: Metrics;
  recent_decisions: ExplainRow[];
}

export interface ResetBody {
  preset?: string;
  environment?: Partial<EnvironmentConfig>;
  receiver?: Partial<ReceiverConfig>;
  scheduler?: string;
  scheduler_params?: Record<string, unknown>;
}

export interface Preset {
  name: string;
  description: string;
  environment: EnvironmentConfig;
  receiver: ReceiverConfig;
}

// --------------------------------------------------------------------------- //
export const api = {
  health: () => jget<Health>("/api/health"),
  state: () => jget<SimState>("/api/state"),

  // --- auth ---------------------------------------------------------------- //
  login: (username: string, password: string) =>
    jpost<TokenResponse>("/api/auth/login", { username, password }),
  demo: () => jpost<TokenResponse>("/api/auth/demo"),
  me: () => jget<MeResponse>("/api/auth/me"),
  logout: () => jpost<{ ok: boolean }>("/api/auth/logout"),
  changePassword: (current_password: string, new_password: string) =>
    jpost<{ ok: boolean }>("/api/auth/change-password", {
      current_password,
      new_password,
    }),

  // --- platform: mode / audit / protected bands -------------------------- //
  getMode: () => jget<PlatformMode>("/api/mode"),
  setMode: (mode: "simulation" | "live_es") =>
    jpost<PlatformMode>("/api/mode", { mode, confirm: true }),
  audit: (params?: { actor?: string; action?: string; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.actor) q.set("actor", params.actor);
    if (params?.action) q.set("action", params.action);
    q.set("limit", String(params?.limit ?? 200));
    return jget<{ entries: AuditEntry[] }>(`/api/audit?${q.toString()}`);
  },
  getProtectedBands: () =>
    jget<{ protected_bands: number[] }>("/api/tasking/protected-bands"),
  setProtectedBands: (bands: number[]) =>
    jpost<{ protected_bands: number[] }>("/api/tasking/protected-bands", { bands }),

  // --- admin: users ----------------------------------------------------- //
  users: () => jget<{ users: PlatformUser[]; roles: Role[] }>("/api/auth/users"),
  createUser: (username: string, password: string, role: Role) =>
    jpost<{ username: string; role: Role }>("/api/auth/users", {
      username,
      password,
      role,
    }),
  setUserRole: (username: string, role: Role) =>
    jpost<{ username: string; role: Role }>(
      `/api/auth/users/${encodeURIComponent(username)}/role`,
      { role },
    ),
  resetUserPassword: (username: string, new_password: string) =>
    jpost<{ ok: boolean }>(
      `/api/auth/users/${encodeURIComponent(username)}/reset-password`,
      { new_password },
    ),
  deleteUser: (username: string) =>
    jdelete<{ ok: boolean }>(`/api/auth/users/${encodeURIComponent(username)}`),

  // --- hardware / live path ------------------------------------------- //
  hwStatus: () => jget<HardwareStatus>("/api/hardware/status"),
  hwDevices: () =>
    jget<{ devices: HardwareDeviceInfo[] }>("/api/hardware/devices"),
  hwConfig: (config: HardwareConfig) =>
    jpost<Record<string, unknown>>("/api/hardware/config", config),
  hwStart: (config?: Partial<HardwareConfig>) =>
    jpost<HardwareStatus>("/api/hardware/start", config ? { config } : {}),
  hwStop: () => jpost<HardwareStatus>("/api/hardware/stop"),
  hwFrames: (since = -1) =>
    jget<{
      frames: SweepFrameDto[];
      latest_seq: number;
      observations: BandObservation[];
    }>(`/api/hardware/frames?since=${since}`),
  hwRecordings: () =>
    jget<{ recordings: RecordingMeta[] }>("/api/hardware/recordings"),
  hwRecordStart: (name?: string) =>
    jpost<{ recording_id: string; recording: boolean }>(
      "/api/hardware/record/start",
      { name },
    ),
  hwRecordStop: () => jpost<RecordingMeta>("/api/hardware/record/stop"),

  // --- scenarios ------------------------------------------------------- //
  scenarios: () => jget<{ scenarios: Scenario[] }>("/api/scenario"),
  scenarioGet: (id: string) =>
    jget<Scenario>(`/api/scenario/${encodeURIComponent(id)}`),
  scenarioCreate: (body: ScenarioSaveBody) =>
    jpost<Scenario>("/api/scenario", body),
  scenarioUpdate: (id: string, body: ScenarioSaveBody) =>
    jput<Scenario>(`/api/scenario/${encodeURIComponent(id)}`, body),
  scenarioDuplicate: (id: string) =>
    jpost<Scenario>(`/api/scenario/${encodeURIComponent(id)}/duplicate`),
  scenarioDelete: (id: string) =>
    jdelete<{ ok: boolean }>(`/api/scenario/${encodeURIComponent(id)}`),
  scenarioLoad: (id: string) =>
    jpost<SimState>(`/api/scenario/${encodeURIComponent(id)}/load`),

  // --- monte carlo --------------------------------------------------- //
  montecarloRun: (body: {
    scenario_id?: string | null;
    schedulers: string[];
    n_seeds: number;
    steps: number;
  }) => jpost<MonteCarloReport>("/api/montecarlo/run", body),
  montecarloExportUrl: (id: string, fmt: "json" | "csv" | "html") =>
    `${BASE}/api/montecarlo/${id}/export/${fmt}`,

  // --- signal analysis --------------------------------------------- //
  tracks: () => jget<{ tracks: EmitterTrack[]; time_slot: number }>("/api/tracks"),
  track: (id: string) => jget<EmitterTrack>(`/api/tracks/${encodeURIComponent(id)}`),
  anomaly: () => jget<AnomalyReport>("/api/anomaly"),
  forecast: () => jget<ForecastReport>("/api/forecast"),

  // --- library --------------------------------------------------- //
  library: () => jget<{ entries: LibraryEntry[] }>("/api/library"),
  libraryRevisions: (id: string) =>
    jget<{ revisions: LibraryRevisionRow[] }>(
      `/api/library/${encodeURIComponent(id)}/revisions`,
    ),
  libraryCreate: (body: LibraryEntryBody) =>
    jpost<LibraryEntry>("/api/library", body),
  libraryUpdate: (id: string, body: LibraryEntryBody) =>
    jput<LibraryEntry>(`/api/library/${encodeURIComponent(id)}`, body),
  libraryDelete: (id: string) =>
    jdelete<{ ok: boolean }>(`/api/library/${encodeURIComponent(id)}`),

  // --- tasking + alerts ---------------------------------------- //
  watchLists: () => jget<{ watch_lists: WatchListItem[] }>("/api/tasking/watchlists"),
  setWatchLists: (watch_lists: WatchListItem[]) =>
    jpost<{ watch_lists: WatchListItem[] }>("/api/tasking/watchlists", { watch_lists }),
  alertRules: () => jget<{ alert_rules: AlertRuleItem[] }>("/api/tasking/alert-rules"),
  setAlertRules: (alert_rules: AlertRuleItem[]) =>
    jpost<{ alert_rules: AlertRuleItem[] }>("/api/tasking/alert-rules", { alert_rules }),
  alerts: (state?: string) =>
    jget<{ alerts: AlertItem[]; unacked: number }>(
      `/api/alerts${state ? `?state=${state}` : ""}`,
    ),
  ackAlert: (id: string) => jpost<AlertItem>(`/api/alerts/${id}/ack`),
  closeAlert: (id: string) => jpost<AlertItem>(`/api/alerts/${id}/close`),

  // --- direction finding ------------------------------------------- //
  dfNodes: () => jget<{ nodes: ReceiverNode[] }>("/api/df/nodes"),
  setDfNodes: (nodes: Partial<ReceiverNode>[]) =>
    jpost<{ nodes: ReceiverNode[] }>("/api/df/nodes", { nodes }),
  dfFixes: () =>
    jget<{ fixes: GeoFix[]; summary: DFSummary; time_slot: number }>("/api/df/fixes"),
  dfFix: (trackId: string) =>
    jget<GeoFix & { history: Array<{ time_slot: number; x_km: number; y_km: number }> }>(
      `/api/df/fixes/${encodeURIComponent(trackId)}`,
    ),
  dfHealth: () => jget<DFHealth>("/api/df/health"),

  schedulers: () =>
    jget<{ schedulers: string[]; learning_schedulers: string[] }>("/api/schedulers"),
  presets: () => jget<{ presets: Preset[] }>("/api/presets"),

  reset: (body: ResetBody) => jpost<SimState>("/api/simulation/reset", body),
  step: (count = 1) => jpost<SimState>("/api/simulation/step", { count }),
  run: (steps: number, scheduler?: string, reset = true) =>
    jpost<SimState>("/api/simulation/run", { steps, scheduler, reset }),

  train: (scheduler: string, episodes: number, steps_per_episode: number) =>
    jpost<TrainingReport>("/api/simulation/train", {
      scheduler,
      episodes,
      steps_per_episode,
      vary_seed: true,
    }),
  trainingRuns: () => jget<{ runs: TrainingReport[] }>("/api/training/runs"),

  datasetGenerate: (name?: string, config?: Partial<EnvironmentConfig>) =>
    jpost<DatasetMeta>("/api/dataset/generate", { name, config }),
  datasetList: () => jget<{ datasets: DatasetMeta[] }>("/api/dataset/list"),
  datasetGet: (id: string) => jget<DatasetMeta>(`/api/dataset/${id}`),
  datasetPreview: (id: string) =>
    jget<{
      dataset_id: string;
      time_slots: number;
      bands: number;
      occupancy: number[][];
      power_db: number[][];
    }>(`/api/dataset/${id}/preview`),
  datasetLoad: (id: string, scheduler?: string) =>
    jpost<SimState>(`/api/dataset/${id}/load`, { scheduler }),

  comparisonRun: (schedulers: string[], steps: number, seed?: number) =>
    jpost<ComparisonReport>("/api/comparison/run", { schedulers, steps, seed }),
  comparisonLast: () => jget<ComparisonReport>("/api/comparison/last"),
  comparisonExportUrl: (fmt: "json" | "csv" | "html") =>
    `${BASE}/api/comparison/export/${fmt}`,

  explainabilityLog: (limit = 200) =>
    jget<{ log: ExplainRow[] }>(`/api/explainability/log?limit=${limit}`),

  runReport: () => jget<RunReport>("/api/report/run"),
  runReportExportUrl: (fmt: "json" | "csv" | "html") =>
    `${BASE}/api/report/run/export/${fmt}`,
};

export const ALL_SCHEDULERS = [
  "round_robin",
  "random",
  "priority",
  "epsilon_bandit",
  "ucb_bandit",
  "thompson",
  "q_learning",
];
