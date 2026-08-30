// Typed API client for the SPECTRA-SCAN AI backend.
// Vite proxies /api -> http://127.0.0.1:8000 in dev (see vite.config.ts).

const BASE = import.meta.env.VITE_API_BASE ?? "";

async function jget<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${path} -> ${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

async function jpost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok) throw new Error(`${path} -> ${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

// --------------------------------------------------------------------------- //
export interface Health {
  status: string;
  mode: string;
  transmit_capability: boolean;
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
  running: boolean;
  done: boolean;
  time_slot: number;
  max_slots: number;
  scheduler: string;
  available_schedulers: string[];
  dataset_id: string | null;
  preset: string | null;
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
    threshold_db: number;
    threat_prior: number[];
    predicted_activity: number[];
  };
  waterfall: { start_slot: number; power_db: number[][]; active: number[][] };
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
