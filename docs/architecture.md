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

## Roadmap

- **Step 2** — priority score, ε-greedy bandit, UCB1, Thompson, Q-learning; reward
  shaping; explainability payloads.
- **Step 3** — DeepSense-style dataset generator + replay; strategy comparison engine; report export.
- **Step 4** — full dashboard (Live Monitor, Strategy Comparison, Dataset Lab, Training Runs, Explainability Log, Reports).
- **Step 5** — scenario presets, metric hardening, expanded tests, judge-ready README + demo script.
