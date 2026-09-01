# SPECTRA-SCAN AI — Validation

How the numbers this platform reports are defined, tested, and protected from
regression, plus the receive-only hardware-in-the-loop (HIL) test plan.

---

## 1. Metric definitions & tests

Every metric has (a) a one-line definition in
[`REFERENCE.md`](REFERENCE.md) §I.9 / §I.9a, (b) an independent reimplementation
in `backend/app/metrics/split.py`, and (c) a test in
`backend/tests/test_ext_step8.py` that recomputes it from the raw per-step
history and asserts equality with the live `MetricsTracker` snapshot.

### 1.1 Simulation metrics (need synthetic ground truth)

| Metric | Definition |
| --- | --- |
| `probability_of_detection` | hits / scans that landed on a truly active band |
| `false_alarm_rate` | false alarms / scans that landed on an inactive band |
| `interception_ratio` | distinct emitter events detected ≥1× / events begun so far |
| `average_intercept_delay` | mean `first_detection_slot − event.start` over detected events (slots) |
| `high_priority_detection_rate` | high-priority events detected / high-priority events begun (high priority = flag or threat ≥ 0.7) |
| `missed_opportunity_count` | Σ over steps of (active bands this slot ≠ the scanned band) |
| `correct_prediction_percentage` | 100 · correct `predicted_active` flags / steps that carried a prediction |
| `scan_coverage` | distinct bands scanned / total bands *(shared with live)* |
| `average_revisit_time` | mean gap (slots) between consecutive visits to a band *(shared with live)* |
| `detection_under_effect_rate` | real signals detected while a simulated EW effect covered the band / such scans |
| `spoof_deception_rate` | "detections" on truth-inactive, effect-covered bands / synthetic-effect scans |
| `df_cep_km` / `df_rmse_km` | median / RMS geolocation error vs truth position |

In `live_es` mode these read `n/a`.

### 1.2 Live metrics (no ground truth)

| Metric | Definition |
| --- | --- |
| `occupancy_estimate` | share of scans flagged above threshold — no truth claim |
| `scan_coverage`, `average_revisit_time` | as above |
| `average_observed_snr_db` | mean measured SNR over scans that cleared threshold |
| `above_threshold_detections` | count of scans the receiver flagged (detection or false alarm) |
| `average_proxy_reward` | mean of `compute_proxy_reward()` per step — rewards stable above-threshold detections, penalises empty scans / excess retuning |
| `recording_duration_s`, `frame_rate_hz` | from the SDR source (n/a in pure sim) |
| `alerts_open`, `alerts_total` | alert counters |
| `policy_vs_shadow_margin` | online-policy proxy-reward EMA − priority shadow EMA |

Served at `GET /api/report/metrics/split`.

---

## 2. Benchmark suite (CI gate)

`backend/scripts/benchmark.py` — a **frozen** matrix:

- presets: `Periodic Radar-Like Challenge`, `Frequency Hopping Challenge`,
  `Dense Emitter Environment`
- schedulers: `round_robin`, `priority`, `ucb_bandit`
- seeds: preset seed `+ {0, 101, 202}`; 400 steps each

`run_benchmark()` returns per-cell mean / std / 95 % CI and cross-preset
**headline means**. `check_bands()` compares the headlines to `HEADLINE_BANDS`.

### 2.1 Reference headline numbers (3 seeds × 400 steps)

| scheduler | avg reward | interception | P(det) | missed opp. |
| --- | ---: | ---: | ---: | ---: |
| `round_robin` | −52.7 | 0.076 | 0.858 | 3001 |
| `priority` | **−43.1** | 0.045 | **0.908** | **2783** |
| `ucb_bandit` | −51.5 | 0.076 | 0.849 | 2999 |

The cross-preset mean is dominated by the dense preset (many simultaneously
active bands ⇒ large unavoidable missed-opportunity penalty); read the
per-preset deltas, not the absolute value.

### 2.2 Per-preset (priority vs round_robin, average reward)

| preset | round_robin | priority | Δ |
| --- | ---: | ---: | ---: |
| Periodic Radar-Like Challenge | −19.2 | −6.7 | **+12.5** |
| Frequency Hopping Challenge | −51.1 | −47.8 | **+3.3** |
| Dense Emitter Environment | −87.8 | −74.9 | **+12.9** |

### 2.3 The gate — `backend/tests/test_ext_step8_benchmark.py`

Fails if:

1. the matrix stops being **deterministic** (two runs must be identical),
2. any headline number drifts **outside its `HEADLINE_BANDS` tolerance**, or
3. `priority` stops beating `round_robin` on average reward on **any** preset.

Regenerate the bands after an intentional change:
`python -m scripts.benchmark --emit-bands`.

---

## 3. Ablation

`backend/scripts/ablation.py` — every available scheduler vs the `round_robin` /
`random` baselines across **every** preset, mean ± 95 % CI, plus the
average-reward delta against each baseline. Writes `data/ablation/latest.json`.

### 3.1 Result (6 presets, 3 seeds × 300 steps, mean Δ average reward vs `round_robin`)

| scheduler | mean Δ vs round_robin |
| --- | ---: |
| `priority` | **+7.1** |
| `contextual_bandit` | +3.4 |
| `thompson` | +3.2 |
| `epsilon_bandit` | +3.0 |
| `q_learning` | +1.7 |
| `ucb_bandit` | +0.7 |
| `random` | −0.0 |

Every adaptive scheduler beats the open-loop sweep on average reward across the
preset set; `priority` is the strongest out of the box. `dqn` / `drqn` are
included when `torch` is installed.

---

## 4. Sim-to-real calibration method

`backend/app/sim2real/calibrate.py`:

1. Take a receive-only **recording** (or `file_replay` session).
2. Estimate the environment's statistics: noise-floor distribution, fading
   variance, per-bin false-alarm rate, occupancy fraction, SNR spread.
3. Fit the simulator's `noise_floor_db`, fading model and `false_alarm_prob` so a
   fresh `RFEnvironment` reproduces those statistics; save a `CalibrationProfile`
   (`data/sim2real/<id>.json`).

`sim2real/gap.py` then runs the **same scheduler** on (a) the recording via
replay and (b) the calibrated sim, and reports a **reality-gap score** per metric
(distribution distance) plus a short automatic narrative. Identical recording vs
its own calibrated sim → near-zero gap; a mismatched profile → a larger gap,
monotonic in the injected mismatch (`test_ext_step6.py`).

---

## 5. HIL (receive-only) test plan + shielded-lab SOP

> **Receive-only.** Nothing below transmits. The platform has no transmit code
> and none is to be added. If a known signal is required to exercise the receive
> chain, generate it with **separate, self-contained lab equipment** in a
> shielded, cabled, attenuated setup — never through this software.

### 5.1 Bench setup (BOM)

- 1× receive-only SDR: RTL-SDR v3, or HackRF One (**RX sweep only**), or a
  USRP/SoapySDR device.
- Shielded enclosure or fully cabled path; **50 Ω dummy loads** on all unused
  ports.
- Fixed attenuators (e.g. 30–60 dB) between any signal source and the receiver so
  no port ever sees more than its rated input.
- A separate, isolated reference-signal generator **owned and operated
  independently** of this platform, on a band you are licensed / permitted to
  use, terminated into the cabled path — never radiating.
- Interlock: power to any source is keyed and cannot be enabled while an antenna
  (rather than a dummy load / cabled path) is connected.

### 5.2 Procedure

1. **Tool check.** `GET /api/hardware/devices` — confirm the adapter reports
   `receive_only: true` and the binary is found. If missing, the UI shows the
   install hint and the sim path still runs.
2. **Noise-floor baseline.** Start the source **off**, `POST /api/hardware/start`
   for the target range, record ~60 s. Confirm the DSP noise-floor estimate is
   stable and `occupancy_estimate ≈ 0`.
3. **Known CW tone (cabled, attenuated).** Enable the reference source at a known
   frequency and level. Confirm: the correct band flags active, measured SNR is
   within tolerance of `level − noise_floor`, and the scheduler parks on it.
4. **Stepped frequency.** Move the tone across 3–4 bands; confirm hop detection
   and that a single `EmitterTrack` follows it (id preserved).
5. **Replay parity.** Stop; replay the recording via `file_replay`. Confirm the
   dashboard, tracks and metrics match the live run (this is the property the
   demo relies on).
6. **Calibrate.** Run `POST /api/sim2real/calibrate` on the recording, then
   `POST /api/sim2real/gap` with the session scheduler; confirm a small gap
   score and a sensible narrative.
7. **Air-gap.** From the same host, `python -m scripts.preflight` →
   `0 outbound connections`.
8. **Evidence.** Finish the session, `GET /api/evidence/{id}`, verify the
   manifest checksums (`verify_evidence_pack`).

### 5.3 Pass criteria

- No transmit symbol anywhere under `backend/app/hardware/` (`test_ext_step2*`).
- Known-tone band flagged correctly; measured SNR within ± a few dB of expected.
- Stepped tone yields one track, not many.
- `file_replay` of the capture reproduces the live dashboard.
- `scripts/preflight.py` reports zero egress.
- Evidence-pack checksums verify.

---

## 6. Known limitations

- Single-run sessions carry no CI; the mission report's scheduler-vs-baseline
  sub-table adds one by re-running the scenario (3 seeds).
- The benchmark cross-preset mean is dominated by the densest preset — use the
  per-preset deltas for claims.
- Propagation / fading / PRI / antenna models are first-order and seeded.
- Classification and library matching are trained on synthetic data only.
- DF assumes the configured node geometry and noise model; multipath is not
  modelled.
- `dqn` / `drqn` require `torch`; without it they report "torch required" and the
  rest of the platform is unaffected.
