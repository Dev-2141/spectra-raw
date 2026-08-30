// Thin API client for the SPECTRA-SCAN AI backend.
// During dev, Vite proxies /api -> http://127.0.0.1:8000 (see vite.config.ts).

const BASE = import.meta.env.VITE_API_BASE ?? "";

async function jget<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

async function jpost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

export interface Health {
  status: string;
  product: string;
  mode: string;
  transmit_capability: boolean;
}

export interface Metrics {
  steps: number;
  average_reward: number;
  probability_of_detection: number;
  false_alarm_rate: number;
  interception_ratio: number;
  average_intercept_delay: number;
  high_priority_detection_rate: number;
  missed_opportunity_count: number;
  scan_coverage: number;
  average_revisit_time: number;
  correct_prediction_percentage: number;
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
  spectrum: {
    time_slot: number;
    power_db: number[];
    active: number[];
    threshold_db: number;
    threat_prior: number[];
    predicted_activity: number[];
  };
  waterfall: { start_slot: number; power_db: number[][]; active: number[][] };
  scan_path: Array<{
    time_slot: number;
    band: number;
    scanned_band: number;
    detected: boolean;
    false_alarm: boolean;
    true_active: boolean;
    reward: number;
  }>;
  reward_series: Array<{ time_slot: number; reward: number }>;
  metrics: Metrics;
  last_step?: {
    time_slot: number;
    reward: number;
    reward_breakdown: Record<string, number>;
    retuned: boolean;
    decision: {
      selected_band: number;
      scheduler: string;
      confidence: number;
      predicted_active: boolean | null;
      reasons: string[];
      alternatives: number[];
      explanation: string;
    };
    detection: {
      band: number;
      true_active: boolean;
      detected: boolean;
      false_alarm: boolean;
      measured_snr_db: number;
    };
  } | null;
  steps_executed?: number;
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

export interface DatasetMeta {
  dataset_id: string;
  created_at: string;
  name: string;
  number_of_bands: number;
  number_of_time_slots: number;
  stats: {
    occupancy_percentage: number;
    active_band_count: number;
    active_time_count: number;
    emitter_type_distribution: Record<string, number>;
    average_snr_db: number;
    threat_distribution: Record<string, number>;
    sparsity_score: number;
  };
}

export interface ComparisonReport {
  scenario_seed: number;
  replayed_dataset: string | null;
  number_of_bands: number;
  steps: number;
  winner: string;
  ranking: string[];
  score_weights: Record<string, number>;
  metrics_table: Array<{
    scheduler: string;
    rank: number;
    weighted_score: number;
    probability_of_detection: number;
    false_alarm_rate: number;
    interception_ratio: number;
    average_intercept_delay: number;
    average_reward: number;
    high_priority_detection_rate: number;
    missed_opportunity_count: number;
    scan_coverage: number;
  }>;
  entries: Array<{
    scheduler: string;
    series: {
      time_slot: number[];
      average_reward: number[];
      detection_rate: number[];
      interception_ratio: number[];
      scan_coverage: number[];
    };
  }>;
}

export const api = {
  health: () => jget<Health>("/api/health"),
  state: () => jget<SimState>("/api/state"),
  schedulers: () =>
    jget<{ schedulers: string[]; learning_schedulers: string[] }>("/api/schedulers"),
  reset: (body?: unknown) => jpost<SimState>("/api/simulation/reset", body),
  step: (count = 1) => jpost<SimState>("/api/simulation/step", { count }),
  run: (steps: number, scheduler?: string) =>
    jpost<SimState>("/api/simulation/run", { steps, scheduler, reset: true }),
  train: (scheduler: string, episodes = 10, steps_per_episode = 500) =>
    jpost<TrainingReport>("/api/simulation/train", {
      scheduler,
      episodes,
      steps_per_episode,
      vary_seed: true,
    }),
  datasetGenerate: (name?: string) =>
    jpost<DatasetMeta>("/api/dataset/generate", name ? { name } : {}),
  datasetList: () => jget<{ datasets: DatasetMeta[] }>("/api/dataset/list"),
  datasetLoad: (id: string, scheduler?: string) =>
    jpost<SimState>(`/api/dataset/${id}/load`, { scheduler }),
  comparisonRun: (schedulers: string[], steps = 1000, seed?: number) =>
    jpost<ComparisonReport>("/api/comparison/run", { schedulers, steps, seed }),
  comparisonExportUrl: (fmt: "json" | "csv" | "html") =>
    `/api/comparison/export/${fmt}`,
};
