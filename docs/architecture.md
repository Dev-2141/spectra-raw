# SPECTRA-SCAN AI — Architecture Notes

Dual-mode: **simulation** (seeded synthetic ground truth) and **live_es**
(receive-only SDR / recording). Both drive the identical dashboard; the metric
set differs (see [`VALIDATION.md`](VALIDATION.md)).

## Design goals

1. **Deterministic, reproducible scenarios.** Given a seed, the entire
   simulation ground truth (occupancy / SNR / power / threat matrices, emitter
   list, propagation, node geometry) is fixed. Schedulers and the receiver use
   *separate* RNG streams. Strategy comparison, Monte Carlo and the benchmark are
   bit-reproducible for a given seed set.
2. **Strict information boundary.** A scheduler sees a `SchedulerContext` with
   only what a real receive-only sensor could know: its own visit / hit / miss /
   false-alarm counts, last-visit slots, a running activity estimate, static
   library-style threat priors, tasking weights, forecast hints, recent reward.
   It never sees `env.occupancy`.
3. **Receive-only hardware.** No SDR TX path anywhere; `HardwareAdapter` exposes
   no transmit method; `/api/health` → `transmit_capability: false`.
4. **Simulation-only EW effects.** `app/simulation/ew_effects.py` cannot import
   `app/hardware` (enforced by `test_ext_step3.py`).
5. **Air-gapped.** No outbound socket during a full smoke run
   (`scripts/preflight.py`).

## Request pipeline (`app/main.py`)

```
HTTP -> CORS
     -> platform_middleware:
          /api/v1/<x>            rewritten to /api/<x>        (frozen v1 alias)
          per-IP sliding-window rate limit (SPECTRA_RATE_LIMIT_RPM; testclient exempt)
          security headers: X-Content-Type-Options nosniff, X-Frame-Options DENY,
                            Referrer-Policy no-referrer, CSP default-src 'self'
     -> router (viewer role at the router level; mutations also audit)
```

In production (`SPECTRA_SERVE_FRONTEND=1`) the built frontend is served as static
files from the backend — no separate web server, no CDN.

## Data flow per `Simulation.step()`

```
[live_es only] env.ingest_step(t): pull newest DSP BandObservations into slot t
scheduler.decide(context)         -> ScanDecision (+ reasons, alternatives, counterfactual)
_apply_protected_guard(...)       -> redirect off a never-scan band (audited)
receiver.tune(band)               -> retune flag + cooldown
receiver.observe(env, t, band)    -> measurement (true_active, detected, false_alarm, SNR, power)
[effects] score vs occupancy_truth; a "detection" on synthetic energy = deception
compute_reward(...)               -> scalar reward + per-component breakdown
update running estimates (visit/hit/miss/FA counts, predicted_activity EWMA)
scheduler.update(feedback)
metrics.record(...)               -> SchedulerMetrics snapshot (up_to_t)
on_step_hook(sim, result)         -> online-learning guardrail (live), if enabled
t += max(1, dwell_slots)
_publish_and_record(state, results):
   stream hub  <- "state" event
   session store <- decisions[] + metrics row   (when a session is recording)
```

## Live-ES path

- `app/hardware/` adapters produce `SweepFrame`s; `HardwareManager` owns the
  active adapter, a bounded frame ring buffer and a background reader thread.
- `app/dsp/process.py` turns frames into `list[BandObservation]`: rolling-
  percentile noise floor, CFAR-style per-bin occupancy, bin→band aggregation
  onto the configured grid, per-band SNR, multi-frame exponential smoothing, hop
  detection between frames.
- `app/simulation/live_env.py::LiveRFEnvironment` implements the surface
  `Simulation` expects from `RFEnvironment`, sourced from `HardwareManager` +
  `dsp`. Ground-truth-only metrics report `n/a`.

## Streaming (`app/stream/hub.py`, Step 7)

- `StreamHub` fan-out with a per-subscriber bounded queue and a monotonic
  per-type sequence number.
- Events: `state`, `decision`, `metric`, `alert`. Backpressure drops the oldest
  `state`/`metric` for a slow subscriber; **`alert` is never dropped**.
- `WS /ws?token=<jwt>`: authenticated at connect. The frontend `useSim` hook
  opens it for server-push refresh with a 2.5 s reconnect and **REST polling as
  the fallback**; the header shows `live ⇅ / polling / offline`. Vite proxies
  `/ws` in dev.

## Storage & sessions (`app/store/sessions.py`, Step 7)

- `SessionStore.start()` → per-step `record("decisions"|"metrics", rows)` →
  `finish()` flushes to `data/sessions/<id>/`:
  - `<kind>.parquet` when `pyarrow` is present, else `<kind>.jsonl.gz`
  - `meta.json` (mode, scenario, scheduler, timestamps, row counts, format)
  - a row in the SQLite `sessions` index
- `finish()` also snapshots the final **tracks / alerts / DF fixes** so a mission
  report is populated even though only decisions+metrics stream per step.
- `schema_version = 1` on **every** row. `GET /api/sessions[/{id}[/data/{kind}]]`;
  `/{id}/export` → a signed `.zip` (Parquet/JSONL + `manifest.json` per-file
  SHA-256 + `DATA_SCHEMA.md`). `POST /api/sessions/import` verifies every
  checksum and rejects a `schema_version` or zip mismatch.
- See [`DATA_SCHEMA.md`](DATA_SCHEMA.md).

## Direction finding (`app/df/`, Step 5)

- `nodes.py` — `ReceiverNode` registry. Simulation: nodes placed in the
  `Scenario`. Live: a node registers via `POST /api/df/register` (LAN, shared
  key) and pushes per-band bearing/TDOA observations.
- `solvers.py` — TDOA multilateration (least-squares + grid refine) and AOA
  bearing intersection → position + covariance → 95 % error ellipse; AOA and
  TDOA can be mixed.
- `sync.py` — GPSDO/PTP sync quality per node degrades the ellipse.
- `fusion.py` — combine a track's per-node observations over time
  (recursive least-squares / EKF) → position history.
- Simulation computes true TOA/AOA per node from geometry + propagation, adds the
  configured noise, and feeds the **same fusion code** as live. Metrics: CEP /
  RMSE vs truth (sim), ellipse area, node-contribution count.

## RL, online learning, sim-to-real (`app/rl/`, `app/sim2real/`, Step 6)

- `rl/envs.py` — Gym-style, vectorisable, seeded wrapper over `Simulation`.
- `rl/train.py` — async training jobs (`POST /api/rl/train`), replay buffer,
  target net, checkpoints to `data/rl/`, learning curves. `rl/curriculum.py`
  trains across presets in increasing difficulty.
- `rl/online.py` — in `live_es`, a trained policy may update from the
  **proxy reward** (stable-detection +, rediscovery +, empty-scan −,
  excess-retune −, uncertainty bonus). Guardrail: run `priority` as a **shadow**
  baseline; if the online policy's rolling proxy reward drops below the shadow by
  a margin for a window, auto-revert to `priority` and raise a `critical` alert.
  All transitions audited.
- `sim2real/calibrate.py` — fit the sim's noise floor / fading / false-alarm
  parameters to a recording → a `CalibrationProfile`. `sim2real/gap.py` — run the
  same scheduler on the recording (replay) and on the calibrated sim → a
  **reality-gap score** per metric (distribution distance) + a short narrative.
- Explainability++: every decision payload also carries a `counterfactual`
  (next-best band + the single factor that would flip the choice);
  `GET /api/explain/policy` returns a band×feature attribution grid (and a
  Q-value-per-band vector for DQN).

## Metrics & validation (Step 8)

- `app/metrics/tracker.py` — incremental `SchedulerMetrics`.
- `app/metrics/split.py` — the frozen `SIM_METRICS` / `LIVE_METRICS` split with
  per-metric definitions, plus `recompute_sim_metrics` / `recompute_live_metrics`
  that rebuild every metric from the raw per-step history with no shared state
  (`test_ext_step8.py` asserts equality with the live snapshot).
- `app/reporting.py` — `build_mission_report(session_id)` +
  `mission_report_to_html` (self-contained, hand-built SVG line/bar charts).
- `app/evidence.py` — `build_evidence_pack(session_id)` → `.zip` +
  `verify_evidence_pack`.
- `scripts/benchmark.py` — frozen matrix, `HEADLINE_BANDS`, `check_bands`;
  `test_ext_step8_benchmark.py` is the CI gate.
- `scripts/ablation.py` — every scheduler vs the two baselines across every
  preset, mean ± 95 % CI.

## Frontend

- `src/useSim.ts` — one hook owns live `SimState`, the `/ws` connection (+
  polling fallback + play loop), and the `reset / step / run` controls. All views
  read from it.
- `src/api.ts` — typed client. `<a href>` can't carry the bearer token, so
  `downloadAuthed()` / `openAuthed()` fetch the bytes with the auth header and
  hand the browser a blob URL (used for the mission report / evidence pack).
- `src/charts.tsx` — dependency-free responsive charts. `LineChart` uses HTML
  y-axis labels + `vectorEffect="non-scaling-stroke"` so a stretched viewBox
  keeps crisp text and 1 px lines.
- `src/views/*` — one file per tab. `BriefMode.tsx` is a full-screen,
  keyboard-driven walk-through (toggle with `b`) that mirrors [`DEMO.md`](DEMO.md).

## Packaging (Step 7)

- `Dockerfile` — multi-stage, single image (frontend build → static, backend).
- `docker-compose.yml` — internal network, **no egress**.
- `deploy/spectra.service` — systemd unit with `IPAddressDeny=any`.
- `scripts/install_offline.{sh,ps1}` — one-shot offline install.
- `scripts/preflight.py` — monkeypatches `socket.connect`, runs a full smoke,
  asserts zero outbound connections.
