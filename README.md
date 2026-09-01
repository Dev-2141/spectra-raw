# SPECTRA-SCAN AI

**Adaptive, Explainable, Receive-Only Spectrum-Surveillance Platform — for RF research and live field testing.**

A dual-mode platform for the Electronic Support (ES) *scan-scheduling* problem: an
observer with limited instantaneous bandwidth must keep deciding **which band to
look at next**, how long to dwell, and how to learn from what it hears.

- **Simulation mode** — a seeded synthetic RF world: emitters, propagation,
  *simulated* EW effects, multi-node geometry. Everything is ground-truthed, so
  every metric is exact and every run is reproducible.
- **Live-ES mode** — the same dashboard driven by a **receive-only** SDR
  (`rtl_power`, `hackrf_sweep` RX, SoapySDR RX) or a recorded sweep file. No
  ground truth, so a separate *proxy* metric set applies.

> ## Safety & scope — load-bearing
>
> This platform is **receive-only in hardware** and **transmit-only in
> simulation**.
>
> - **No transmit code anywhere.** No `hackrf_transfer`, no TX SoapySDR/UHD
>   streams, no IQ playback, no tone/sweep/carrier generation to a device. The
>   hardware adapter base class exposes **no** transmit method.
> - **No jamming/spoofing/DF-for-targeting against real RF.** "Simulated EW
>   effects" (`barrage_noise`, `spot_jam`, `swept_jam`, `repeater_ghost`,
>   `spoof_track`) exist **only inside the simulator** — they produce numbers in
>   a matrix, never RF, and the module cannot import the hardware layer.
> - **No payload decode.** Occupancy, power, PRI, modulation-class and bandwidth
>   estimates only.
> - **All data synthetic.** No real, operational, or classified emitter
>   libraries; every library/track record carries `synthetic: true`.
> - **No outbound network.** Runs fully air-gapped — no CDNs, telemetry, license
>   checks, or model downloads.
>
> **Enforcement:** `GET /api/health` always returns `transmit_capability: false`
> and `hardware_mode: "receive_only"`. `backend/tests/test_ext_step2*.py` greps
> `backend/app/hardware/` for the forbidden symbols and fails if any appear;
> `test_ext_step3.py` asserts `app.simulation.ew_effects` cannot import
> `app.hardware`; `backend/scripts/preflight.py` asserts zero outbound sockets
> during a full smoke run. See [`docs/SECURITY.md`](docs/SECURITY.md).

---

## Contents

| Doc | What it covers |
| --- | --- |
| [`docs/REFERENCE.md`](docs/REFERENCE.md) | Every module / class / function + the theory (detection, propagation, CFAR, bandits, DQN, TDOA/AOA + covariance, proxy reward, sim-to-real gap, every metric formula). |
| [`docs/architecture.md`](docs/architecture.md) | Data flow for both modes, `/ws` streaming, storage, DF, RL, packaging. |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Auth model, roles, audit, air-gap posture, production checklist, data-at-rest. |
| [`docs/VALIDATION.md`](docs/VALIDATION.md) | Benchmark method + CI gate, ablation results, metric definitions + tests, sim-to-real calibration, HIL (receive-only) test plan + shielded-lab SOP. |
| [`docs/DATA_SCHEMA.md`](docs/DATA_SCHEMA.md) | Every persisted record, field types, units, `schema_version`. |
| [`docs/DEMO.md`](docs/DEMO.md) | The 12-step judge demo script. |

---

## 1. Platform overview

Two services:

- **Backend** — Python 3.11 + FastAPI. Owns the synthetic RF world, the
  receive-only hardware layer + DSP, the schedulers, reward/metrics, analysis
  (classification, tracks, anomaly, forecast), the synthetic emitter library,
  tasking + alerting, multi-node direction finding, RL training + online
  learning, sim-to-real calibration, durable sessions, `/ws` streaming, mission
  reporting, and the evidence pack. Core demo path is pure
  NumPy / Pandas / scikit-learn; **PyTorch and pyarrow are optional and
  lazy-imported** — absent, the DRL schedulers report "install torch to enable"
  and everything else still runs.
- **Frontend** — React + Vite + TypeScript, a dense dark "RF analytics"
  dashboard. Charts are **hand-built responsive SVG / canvas** in
  `frontend/src/charts.tsx` — no chart library.

```
backend/app/
  main.py            FastAPI app: CORS, /api/v1 alias, rate limit, security headers, prod frontend
  config.py          typed settings from env (Appendix C in the build prompt)
  auth/              local user store (Argon2), JWT, RBAC, demo token
  audit/             append-only audit table + daily JSONL
  modes/             ModeManager  (simulation | live_es)
  api/               routes + the process-wide SimulationManager
  models/            Pydantic models for every payload
  simulation/        environment, receiver, reward, engine, propagation, emitters,
                     ew_effects (SIM-ONLY), scenario, presets, live_env
  dsp/               noise floor, CFAR occupancy, bin->band, SNR, smoothing, hop detect
  hardware/          receive-only adapters: file_replay, rtl_power, hackrf_sweep, soapysdr;
                     HardwareManager + ring buffer + reader thread   (NO transmit method)
  schedulers/        round_robin, random, priority, epsilon/ucb/thompson bandits,
                     q_learning, contextual_bandit, dqn, drqn (+ registry)
  analysis/          features, classify (sklearn .joblib), tracks, anomaly, forecast
  library/           versioned synthetic EmitterLibrary (SQLite)
  tasking/           watch lists, priority weights, protected bands, alert rules
  alerting/          rule evaluation -> Alert (open|ack|closed)
  df/                nodes, TDOA, AOA, sync quality, fusion  (sim geometry + LAN peers)
  rl/                Gym-style env wrapper, training jobs, curriculum, online guardrail
  sim2real/          calibrate a profile to a recording; reality-gap score
  metrics/           incremental MetricsTracker + split.py (sim vs live + recompute)
  comparison/        strategy comparison + Monte Carlo + export
  store/             durable sessions -> Parquet/JSONL + SQLite index + signed .zip
  stream/            StreamHub: /ws state/decision/metric/alert events, backpressure
  reporting.py       run report + Step 8 mission report (self-contained HTML, SVG)
  evidence.py        evidence pack .zip (session + report + benchmark + SHA-256 manifest)
backend/scripts/     preflight.py (air-gap), benchmark.py (CI gate), ablation.py
frontend/src/
  useSim.ts          central state hook; /ws with polling fallback
  api.ts             typed client; authed blob download/open helpers
  charts.tsx         SpectrumChart, Waterfall, LineChart, BarChart, Sparkline (no deps)
  views/             one file per tab, incl. BriefMode.tsx (full-screen walk-through)
```

## 2. The two modes

| | Simulation | Live-ES |
| --- | --- | --- |
| Spectrum source | seeded `RFEnvironment` ground truth | `SweepFrame`s from a receive-only SDR / recording, via `dsp/` → `BandObservation` |
| Ground truth | yes — exact metrics | none — proxy metrics only |
| EW effects | simulated overlays on the observed spectrum (never on truth) | n/a |
| DF | simulated node geometry + noise model | LAN peer nodes push bearings/TDOA |
| Metrics | `SIM_METRICS` (P(det), FAR, interception, intercept delay, hi-pri rate, missed-opp, correct-%, detection-under-effect, spoof-deception, DF CEP/RMSE) | `LIVE_METRICS` (occupancy estimate, coverage, observed SNR, revisit, above-threshold count, avg proxy reward, frame rate, alert counts, policy-vs-shadow margin) |
| Boot default | **yes** — the platform always boots in `simulation` | switch via the header toggle (operator+, audited) |

The split is frozen in `backend/app/metrics/split.py` and served at
`GET /api/report/metrics/split`; see [`docs/VALIDATION.md`](docs/VALIDATION.md).

## 3. Identity, access control, audit

- Local users in `backend/data/platform.db` (created on first boot). Dev seeds:
  `admin/admin`, `operator/operator`, `analyst/analyst`, `viewer/viewer`, plus a
  read-only `demo`. Passwords hashed with Argon2. Seeds are **off** in
  production.
- Roles: `viewer` < `analyst` < `operator` < `admin`. Every mutating endpoint
  requires a sufficient role **and** writes an append-only audit record. The
  only unauthenticated endpoints are `GET /api/health` and the auth endpoints.
- **Skip (demo):** the login screen's *Skip* button calls `POST /api/auth/demo`
  for a read-only `viewer` token with a `demo: true` claim. The demo session can
  read everything and run the simulation, but is `403` on any hardware / config
  / user / library / scenario mutation. A persistent amber banner shows
  `DEMO MODE`.
- Login screen also offers dev-only "enter as `<role>`" quick-login buttons
  (`POST /api/auth/quick-login`), hidden entirely in production.
- `GET /api/audit` (operator+) is filterable, paginated, CSV/JSONL export. There
  is no update or delete path.

See [`docs/SECURITY.md`](docs/SECURITY.md).

## 4. Receive-only hardware inputs

All adapters live in `backend/app/hardware/` and share `HardwareAdapter`
(`list_devices / is_available / start_scan / stop_scan / read_frame /
get_status`). **The base class has no transmit method.**

| Source | Binary / lib | Notes |
| --- | --- | --- |
| `file_replay` | none | **Default + demo path.** Replays a recorded sweep CSV/JSONL at real or accelerated cadence; loops or stops at EOF. A recording is a valid input here and to the Dataset Lab. |
| `rtl_power` | `rtl_power` on `PATH` | Spawned **RX-only** for the configured range; CSV parsed to `SweepFrame`. Missing binary → specific install hint, falls back to `file_replay` / `simulation`. |
| `hackrf_sweep` | `hackrf_sweep` on `PATH` | **`hackrf_sweep` only, never `hackrf_transfer`.** Module docstring lists every subprocess arg and asserts RX-only. Same fallback behaviour. |
| `soapysdr` | SoapySDR (flag `FLAG_SOAPYSDR`) | RX `setupStream(SOAPY_SDR_RX, …)` / `readStream` only; PSD via Welch → `SweepFrame`. Unavailable if the module can't import. |

`dsp/` turns frames into `list[BandObservation]` (rolling-percentile noise floor,
CFAR-style per-bin occupancy, bin→band aggregation, per-band SNR, multi-frame
smoothing, hop detection). In `live_es` mode `Simulation.step()` pulls the newest
observations instead of ground-truth matrices.

Recording: `POST /api/hardware/record/{start,stop}` →
`backend/data/recordings/<id>/frames.jsonl` + `meta.json`.

### Lab reference-signal transmit — documentation only

If you need a known signal to validate the **receive** chain, do it in a
**shielded, cabled, attenuated** setup with dummy loads and interlocks, on a
legal band, per your local regulator. This repo contains **no transmit
implementation** and will not gain one. The receive-side calibration maths lives
in `backend/app/sim2real/calibrate.py` and [`docs/VALIDATION.md`](docs/VALIDATION.md).

## 5. Simulated EW effects (analysis tool, never RF)

`backend/app/simulation/ew_effects.py` models what an adversary transmitter
*would do to our receiver's observation*, entirely inside the simulator:

- `barrage_noise` — raise the noise floor over a range
- `spot_jam` — swamp one band; `swept_jam` — a moving swamp
- `repeater_ghost` — inject a delayed copy of a real emitter into another band
- `spoof_track` — add a plausible but fake emitter track

Each effect has a start/stop time, frequency extent, power and a `label`. Effects
change `power_db`, `snr_db`, `occupancy_observed` and an `is_synthetic_effect`
map — they **do not** touch `occupancy_truth`, so *detection under jamming* and
*was fooled by the spoof* become measurable (`detection_under_effect_rate`,
`spoof_deception_rate`). A test asserts the module cannot import `app.hardware`.

## 6. Run it

Requires **Python 3.11+** and (for the UI) **Node 20+**.

### Backend (dev)

```bash
cd backend
python -m venv .venv
# Windows:  .venv\Scripts\Activate.ps1     macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt            # add -r requirements-optional.txt for torch/pyarrow
uvicorn app.main:app --reload --port 8000
```

- API docs: `http://127.0.0.1:8000/docs` · health: `/api/health`
- All routes are also mounted under `/api/v1/...` (frozen alias, see
  [`docs/architecture.md`](docs/architecture.md)).

### Frontend (dev)

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173  (proxies /api and /ws -> :8000)
```

### Tests

```bash
cd backend
.venv\Scripts\python -m pytest -q        # Windows   (POSIX: python -m pytest -q)
```

### Benchmark CI gate / ablation

```bash
cd backend
.venv\Scripts\python -m scripts.benchmark       # writes data/benchmark/latest.json, checks HEADLINE_BANDS
.venv\Scripts\python -m scripts.ablation        # writes data/ablation/latest.json
```

### Air-gapped / production

```bash
cd backend
SPECTRA_PRODUCTION=1 \
SPECTRA_JWT_KEY=<a-real-secret> SPECTRA_SEED_USERS=0 \
SPECTRA_TLS_CERT=/path/cert.pem SPECTRA_TLS_KEY=/path/key.pem \
SPECTRA_CORS_ORIGINS=https://ops.example.internal SPECTRA_SERVE_FRONTEND=1 \
uvicorn app.main:app --host 0.0.0.0 --port 8443 \
  --ssl-certfile $SPECTRA_TLS_CERT --ssl-keyfile $SPECTRA_TLS_KEY

# prove no egress:
.venv\Scripts\python -m scripts.preflight        # "... 0 outbound connections"
```

`config.validate_production()` refuses to boot with a default JWT key, seed users
on, no TLS, or CORS still allowing localhost. Container + offline installer:
`Dockerfile`, `docker-compose.yml` (internal network, no egress),
`scripts/install_offline.{sh,ps1}`, `deploy/spectra.service`
(`IPAddressDeny=any`).

### Demo entry point

Press **`b`** anywhere in the UI (or the header **▶ Brief** button) for the
full-screen, keyboard-driven walk-through. The click-by-click script is
[`docs/DEMO.md`](docs/DEMO.md).

## 7. Reporting & evidence

- **Run report** — `GET /api/report/run` + `/export/{json,csv,html}`: a snapshot
  of the live simulation.
- **Mission report** — `GET /api/report/mission/{session_id}` (+
  `/export/{json,html}`): per persisted session — summary, the sim/live metric
  split, a scheduler-vs-baseline table with mean ± CI (scenario reconstructed
  from session metadata and re-run), sampled timeline, tracks, DF fixes, alerts,
  hand-built SVG charts, assumptions, limitations. HTML is fully self-contained
  (no external asset references).
- **Evidence pack** — `GET /api/evidence/{session_id}`: a `.zip` of the raw
  session files, the mission report (HTML + JSON), a fresh benchmark JSON,
  `DATA_SCHEMA.md`, and a `manifest.json` with a SHA-256 per entry.
- **Metric definitions** — `GET /api/report/metrics/split`.

The **Reports** tab exposes all of these; **Strategy Comparison** has a
before/after panel (open-loop sweep vs the best adaptive scheduler, three
headline deltas).

## 8. Assumptions log

- One band observed per dwell; retune costs `retune_delay_slots` dead time.
- Reward table is fixed (`docs/REFERENCE.md` §I.5); baselines accrue large
  missed-opportunity penalties because a 1-band receiver cannot cover a wide
  spectrum — read the *relative* gap between strategies.
- `RFEnvironment` ground truth is a seeded function of the config; identical seed
  ⇒ byte-identical scenario. Scheduler and receiver use separate RNG streams.
- Propagation / fading / PRI / antenna models are first-order and seeded, not a
  high-fidelity channel simulation.
- Classification + library matching are trained on **synthetic** data; accuracy
  on real signals is out of scope.
- DF error ellipses assume the configured node geometry and timing/bearing noise
  model; real multipath is not modelled.
- Live-mode metrics are **proxy** measures with no ground-truth validation.
- Simulated EW effects modify the *observed* spectrum only, never
  `occupancy_truth`.

## 9. Limitations

- Even the best scheduler misses most band-slots on a wide spectrum, so absolute
  reward stays negative — compare strategies relative to each other, or use the
  Monte Carlo / benchmark / ablation runners for CI-backed claims.
- Tabular `q_learning` uses a coarse hand-designed state; `priority`,
  `contextual_bandit` and the bandits are stronger out of the box. `dqn`/`drqn`
  need `torch`.
- `file_replay` is the default hardware source; real SDR paths are exercised only
  when the binaries are present.
- Single-run mission reports carry no confidence interval (the scheduler-vs-
  baseline sub-table does, via a re-run).
- The offline map uses a coordinate-grid fallback when raster tiles are absent.

## 10. Safety note (restated)

SPECTRA-SCAN AI models **listening** to a spectrum. It contains **no
transmission, jamming, spoofing, direction-finding-for-targeting, real emitter
libraries, classified data**, or any capability to affect a real RF device, and
makes **no outbound network connection**. It is for research and field testing of
receive-only scan-scheduling algorithms.
