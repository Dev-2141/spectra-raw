# SPECTRA-SCAN AI — Architecture Notes

## Design goals

1. **Deterministic, reproducible scenarios.** Given a seed, the entire ground
   truth (occupancy / SNR / power / threat matrices and the emitter list) is
   fixed. Schedulers and the receiver use *separate* RNG streams so scheduler
   randomness never perturbs the world — this makes strategy comparison fair
   (Step 3).
2. **Strict information boundary.** A scheduler receives a `SchedulerContext`
   containing only what a real receive-only sensor could know: its own visit /
   hit / miss / false-alarm counts, last-visit slots, a running activity
   estimate, static library-style threat priors, and recent reward. It never
   sees `env.occupancy`.
3. **Non-hardware.** No SDR, no RF I/O, no transmission path anywhere.

## Data flow per `Simulation.step()`

```
scheduler.decide(context)  ->  ScanDecision
        |
receiver.tune(band)        ->  retune flag + cooldown
receiver.observe(env,t,b)  ->  measurement (true_active, detected, false_alarm, SNR)
        |
compute_reward(...)        ->  scalar reward + breakdown
        |
update running estimates (visit/hit/miss/FA counts, predicted_activity)
scheduler.update(feedback)
metrics.record(...)        ->  SchedulerMetrics snapshot
        |
t += dwell_slots
```

## Emitter behaviors

| Behavior   | Shape |
| ---------- | ----- |
| `constant` | Long on-blocks covering most of the timeline |
| `burst`    | Short random bursts (1–4 slots) with 6–33 slot gaps |
| `periodic` | Fixed period (9–40), pulse 1–3, random phase — radar-like |
| `hopping`  | Parks on a band for a few slots, then steps ±4 bands |
| `low_duty` | 1–4% duty, 1–2 slot emissions scattered in time |
| `priority` | 3–8% duty intermittent, threat 0.75–1.0 (high value) |

## Metrics definitions (Step 1 baseline; refined in Step 5)

- **Probability of detection** = hits / scans that landed on a truly active band
- **False alarm rate** = false alarms / inactive scans
- **Interception ratio** = detected emitter events / emitter events started so far
- **Average intercept delay** = mean(`first_detection_slot - event_start`) over detected events
- **Scan coverage** = unique scanned bands / total bands
- **Average revisit time** = mean gap between consecutive visits to the same band
- **Missed opportunity count** = Σ over slots of (active bands that slot not equal to the scanned band)
- **Correct prediction %** = correct activity predictions / predictions made
  (baselines make no prediction, so this stays 0 until Step 2)

## Dataset lab & replay (Step 3)

- `app/dataset/generator.py` wraps the same seeded `RFEnvironment` and extracts
  `occupancy / power_db / snr_db / threat / labels / emitter_id` matrices plus a
  `DatasetMeta` sidecar (stats, emitter list, integer label codes).
- `app/dataset/store.py` persists each dataset to
  `backend/data/datasets/<id>/` — `meta.json` + `*.npy` (canonical) + `*.csv`
  mirrors — and rehydrates it via `RFEnvironment(config, prebuilt=...)`
  (`env.replayed == True`), a drop-in for the live generator.
- The `SimulationManager` tracks a `_dataset_id`; while set, every `reset` /
  `run` rebuilds the replay env so the loaded dataset stays active until an
  explicit `environment` config is posted.

## Strategy comparison (Step 3)

- `app/comparison/engine.py` runs each requested scheduler in its own
  `Simulation` seeded identically (or from the same replayed dataset), so the
  ground truth is byte-identical across strategies.
- Per-step `SchedulerMetrics` snapshots (already in `sim.history`) are
  down-sampled into reward / detection-rate / interception / coverage series.
- Winner = weighted score over min-max-normalised metrics:
  `0.35·interception + 0.25·hi-priority + 0.20·avg-reward +
  0.10·(1−missed) + 0.10·(1−delay)`.
- `app/comparison/export.py` renders the cached report as CSV or a standalone
  dark-themed HTML table.

## Dashboard (Step 4)

- `src/useSim.ts` — single `useSim()` hook owns live `SimState`, the play/pause
  loop (HTTP `step` on an interval, N steps/tick from a speed slider), and the
  `reset / step / run` controls. All views read from it.
- `src/ControlSidebar.tsx` — persistent left panel: transport, speed, scheduler,
  environment + receiver config fields, scenario presets, `apply & reset`.
- `src/charts.tsx` — dependency-free responsive charts: `SpectrumChart` (SVG
  bars), `Waterfall` (canvas heatmap + scan-path overlay), `LineChart`
  (multi-series, HTML y-axis labels + `vectorEffect="non-scaling-stroke"` so a
  stretched viewBox keeps crisp text and 1px lines), `BarChart`, `Sparkline`.
- `src/views/*` — one file per tab. Live Monitor is the `[center | right] /
  [log | reward]` grid; the others are full-width.
- Backend additions: `GET /api/explainability/log` (decision log from
  `sim.history`), `GET /api/training/{runs,last}` (manager keeps the last 25
  `TrainingReport`s), `GET /api/report/run[/export/{fmt}]`,
  `GET /api/dataset/{id}/preview` (block-reduced occupancy/power grid for the
  Dataset Lab thumbnail).

## Scenario presets (Step 5)

- `app/simulation/presets.py` holds six named scenarios, each a
  `(RFEnvironmentConfig, ReceiverConfig)` pair plus a code-level description.
  `RFEnvironmentConfig.behavior_weights` lets a preset skew the emitter mix
  (e.g. hopping-heavy, periodic-heavy) without new generator code.
- `GET /api/presets` lists them; `POST /api/simulation/reset {"preset": name}`
  and `POST /api/dataset/generate {"preset": name}` apply one. The
  `SimulationManager` tracks `_preset_name`; an explicit `environment` in a
  reset clears it. Presets exit dataset-replay mode.
- The comparison `SCORE_WEIGHTS` were rebalanced so `average_reward` (the RL
  objective) carries the most weight; `priority` now wins 5 / 6 presets and
  every smart scheduler beats the best baseline on reward across all six.

## Build complete

All five steps are done. Future work would target the limitations in
`README.md` §12 (richer emitter physics, function-approx Q-learning, streaming
telemetry).
