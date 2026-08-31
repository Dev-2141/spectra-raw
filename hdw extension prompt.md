# HDW EXTENSION PROMPT

**SPECTRA-SCAN AI → SPECTRA-SCAN AI: DUAL-MODE RESEARCH PLATFORM**
Adaptive, Explainable, Receive-Only Spectrum-Surveillance Platform for RF Research and Live Field Testing

---

## 0. HOW TO USE THIS PROMPT

You are **extending an existing, working, tested full-stack product**. You are **not** starting from scratch and you are **not** allowed to rebuild what already works.

Build the extension in **exactly 8 steps**. At the end of **every** step you MUST:

1. Run every check that can be run (backend `pytest -q`, backend boot, frontend build, any step-specific smoke test).
2. Print a **"Files changed"** list (added / modified / deleted, one line each).
3. Print a **"Verified"** list (what you actually ran and the result).
4. Print a **"Known issues / deferred"** list.
5. Print the exact commands to run backend, frontend, and tests.
6. **STOP.** Ask the user to type `continue step N`. Do not start the next step on your own.

If a step is too large for one response, stop at a coherent sub-checkpoint, say so explicitly, and wait for `continue step N` (same N).

---

## 1. CURRENT STATE — DO NOT REGRESS

Repo root: this folder. Layout:

```
backend/app/
  main.py            FastAPI app + CORS
  api/               routes + process-wide SimulationManager
  models/            Pydantic models
  simulation/        environment, receiver, reward, engine, presets
  schedulers/        base + baselines + smart + q_learning + registry
  metrics/           incremental MetricsTracker
  dataset/           DeepSense-style generator, store, stats
  comparison/        strategy comparison engine + export
  reporting.py       run-report CSV/HTML
backend/tests/       test_step1..5  (all passing — treat as a regression gate)
frontend/src/
  useSim.ts          central state hook + play loop
  api.ts             fetch wrappers
  ControlSidebar.tsx persistent controls + scenario presets
  charts.tsx         SpectrumChart, Waterfall, LineChart, BarChart, Sparkline (hand-built SVG, NO chart lib)
  ui.tsx             shared primitives
  App.tsx            tab shell
  views/             LiveMonitor, StrategyComparison, DatasetLab, TrainingRuns, ExplainabilityLog, Reports
docs/                architecture.md, DEMO.md, REFERENCE.md
```

Already delivered (original 5-step build): synthetic RF environment + receiver digital twin, reward engine, step engine, **7 schedulers** (`round_robin`, `random`, `priority`, `epsilon_bandit`, `ucb_bandit`, `thompson`, `q_learning`), incremental metrics, DeepSense-style dataset lab, strategy-comparison engine, 6-tab dashboard, 6 scenario presets, run/comparison export (JSON/CSV/HTML), ~75 passing backend tests, judge docs.

### Non-negotiable invariants

- **The existing backend test suite must stay green after every step.** Extend it; never delete or weaken a test to make a step pass.
- **The existing sim-only demo flow must keep working with zero friction** when the user clicks **Skip (demo)** on the new login screen: Live Monitor → pick scheduler → apply & reset → play; Strategy Comparison; Dataset Lab; Explainability Log; Reports.
- **Core stays dependency-light.** Pure NumPy / Pandas / scikit-learn for anything on the demo path. PyTorch is **optional and lazy-imported**; if it is not installed, DRL features must degrade to a clear "install torch to enable" state and everything else must still run.
- **No external network calls anywhere.** The whole platform must run fully **air-gapped**. No CDNs, no telemetry, no license checks, no remote model downloads. Bundle everything.
- **Charts stay hand-built SVG/Canvas** in `charts.tsx` unless a step explicitly authorises a library. If a step needs a new chart, add it to `charts.tsx` in the same style.
- Follow existing patterns: `SimulationManager` singleton, scheduler **registry**, one view file per tab, Pydantic models for every payload.

---

## 2. HARD SAFETY & SCOPE RULES — READ TWICE

This platform is **receive-only in hardware** and **transmit-only in simulation**. That distinction is load-bearing. It must be enforced in code, in the UI, and in the docs.

**Absolutely forbidden — do not write, scaffold, stub, or document how to build:**

- Any code path that makes a real SDR **transmit**: no `hackrf_transfer`, no `tx`/`transmit` SoapySDR streams, no UHD TX, no `writeStream`, no IQ playback to a device, no carrier/tone/sweep generation to hardware.
- Jamming, barrage/spot/swept interference **against real RF**, protocol **spoofing over the air**, signal **injection**, replay-**attack** transmission, DRFM **repeater hardware**, gate pull-off **hardware**, deception **emission**.
- Decoding, demodulating to content, or logging the payload of private/third-party communications. Occupancy, power, PRI, modulation-class, and bandwidth estimates only.
- Real, operational, or classified emitter libraries or captured signal data. **Synthetic / public-style parameters only.**
- Detection-evasion, anti-forensics, or "hide the transmitter" features.
- Any outbound network capability.

**Explicitly allowed and in scope:**

- **Simulated EW effects** — model what a jammer / repeater / spoofer *would do to the spectrum and to the receiver*, entirely inside the RF environment simulator, as an analysis tool for studying detection-under-jamming, scheduler robustness, and counter-measures. This produces **numbers in a matrix, never RF**. It must be impossible for this subsystem to touch a device.
- **Receive-only SDR ingest** from RTL-SDR (`rtl_power`), HackRF (`hackrf_sweep`, RX sweep only), USRP / SoapySDR (RX streaming only), and recorded-file replay.
- **Lab reference-signal transmit** — **documentation only**: BOM, shielded/cabled/attenuated setup, dummy loads, interlocks, legal-band guidance, and the *receive-side* calibration maths. **No transmit implementation of any kind.**

**Enforcement requirements:**

- `GET /api/health` always returns `"transmit_capability": false` and `"hardware_mode": "receive_only"`. A test asserts this and greps the `backend/app/hardware/` tree for the forbidden symbols above and fails if any appear.
- The hardware adapter base class exposes **no** transmit method. Adapters that wrap a transceiver (HackRF) must document, in a module docstring, exactly which library calls are used and that all are RX.
- Every screen shows a persistent status chip: `RECEIVE-ONLY` in Live-ES mode, `SIMULATION` in sim mode.

---

## 3. ENGINEERING STANDARDS (apply to every step)

- **Python:** type hints on all new code; Pydantic v2 models for all request/response bodies; `ruff`-clean; docstrings on public functions and every new module.
- **Tests:** add `backend/tests/test_ext_stepN.py` per step. Unit-test pure logic (DSP, fusion maths, reward, metrics, parsers) against synthetic inputs. Keep the full suite green: `pytest -q`.
- **Frontend:** TypeScript strict; components in the existing style; no new heavy deps without a step authorising it; every new view is a file under `frontend/src/views/` wired into the tab shell.
- **Config:** new module `backend/app/config.py` — a typed settings object read from env with safe defaults. **No secrets in source.** Document every key in Appendix C.
- **Feature flags:** anything heavy (DRL, streaming transport, DF fusion, classification models) sits behind a flag defaulting to the light path so the demo stays fast on a laptop.
- **Auth on everything:** every new endpoint requires a valid session and a sufficient role, and writes an audit entry. The only unauthenticated endpoints are `GET /api/health` and the auth endpoints themselves.
- **Backwards compatibility:** existing endpoints keep their paths and response shapes. If you must change one, add a `v2` path and keep `v1` working until Step 8.
- **Determinism:** every stochastic feature takes an explicit seed and is reproducible. Strategy comparison and Monte Carlo must be bit-reproducible for a given seed set.

---

## 4. CROSS-CUTTING REQUIREMENTS

Applies to all steps, verified again in Step 8:

1. **Mode-awareness:** every feature declares whether it is `sim-only`, `live-only`, or `both`. The UI hides or disables what does not apply to the active mode. Switching mode never crashes an open view.
2. **Explainability parity:** every endpoint that produces a scan decision returns the existing explainability payload shape (`selected_band`, `confidence`, `predicted_active`, `top_reasons[3]`, `alternatives`, `explanation`) — extended, never shrunk.
3. **Auditability:** mode switches, hardware start/stop, config changes, scenario edits, library edits, exports, and login/logout all produce an append-only audit record.
4. **Every metric has a tested definition.** Add the formula to `docs/REFERENCE.md` and a test that recomputes it from raw step/frame history and asserts equality with the live snapshot.
5. **Graceful degradation:** missing SDR tool, missing torch, missing multi-node peers, missing map tiles — each shows a specific, actionable message and never blocks the sim path.

---

## 5. BUILD STEPS

---

### STEP 1 — Identity, Access Control, Mode Spine, Safety Enforcement

**Goal:** put a login wall in front of the product, add role-based access and an append-only audit log, and turn "Simulation vs Live-ES" into a real, guarded, first-class mode context. No RF features yet.

**Backend**

- `backend/app/auth/` package:
  - Local user store in SQLite (`backend/data/platform.db`), created on first boot. Seed users from config: `admin/admin`, `analyst/analyst`, `viewer/viewer`, plus a fixed read-only `demo` user. Passwords hashed with Argon2 (fallback bcrypt). First-login password-change flag for the three non-demo seeds (enforced only for `operator`+ actions, not for the demo path).
  - Roles: `viewer` < `analyst` < `operator` < `admin`. Define a `require_role(min_role)` FastAPI dependency.
  - Sessions: signed JWT (HS256, key from config), 12 h expiry, `/api/auth/login`, `/api/auth/logout`, `/api/auth/me`, `/api/auth/change-password`.
  - `POST /api/auth/demo` — issues a **`demo`/`viewer`** token with a `demo: true` claim. No credentials. Rate-limited. This backs the **Skip** button.
  - `demo` token is barred from: any `POST` that mutates hardware, config, users, library, or scenarios; it may read everything and run simulation.
- `backend/app/audit/` package: `audit(actor, action, target, detail, mode)` → append-only table + daily JSONL file under `backend/data/audit/`. `GET /api/audit` (operator+), filterable, paginated, export CSV/JSONL. Never expose a delete/update path.
- `backend/app/modes/` package: `ModeManager` holding current mode (`simulation` | `live_es`), owned by the app, referenced by `SimulationManager`. `GET /api/mode`, `POST /api/mode` (operator+, audited, confirmation token required). Boot mode is always `simulation`. Switching to `live_es` with no hardware configured is allowed but flagged `degraded`.
- `backend/app/config.py`: typed settings (JWT key, token TTLs, seed-user toggle, feature flags, data dirs, protected-bands default, CORS origins).
- **Protected bands:** config + `POST /api/tasking/protected-bands` (operator+). A never-scan list. Wire a guard into `Simulation.step()` and (later) the hardware scan loop so a scheduler selecting a protected band is overridden to the next-best choice, the event is logged, and the decision explanation notes it.
- Apply `require_role` + `audit` to **all** existing mutating endpoints (`/api/simulation/*`, `/api/dataset/*`, `/api/comparison/*`, training). Reads stay open to `viewer`.
- `GET /api/health`: add `transmit_capability: false`, `hardware_mode: "receive_only"`, `mode`, `version`, `auth: "enabled"`.

**Frontend**

- New `LoginScreen` (pre-shell): username/password form + a prominent **Skip (demo)** button. On skip → call `/api/auth/demo`, store token, enter app with a persistent amber top banner: **"DEMO MODE — read-only, not for operational use"**.
- `api.ts`: attach `Authorization: Bearer` to every call; on 401 bounce to login.
- Top bar: user chip (name, role), **mode switcher** (`SIMULATION` / `LIVE-ES`) gated by role — disabled with a tooltip for `viewer`/`demo`; a confirm dialog for the switch. Persistent `RECEIVE-ONLY` / `SIMULATION` status chip.
- New **Admin** tab (admin only): user list + reset password + role; audit-log viewer with filters and export. Hidden entirely for lower roles.
- All existing views: unchanged behaviour once authenticated; show a small "read-only" hint when the token is `demo` and a control would mutate.

**Tests (`test_ext_step1.py`)**

- login success/failure; token required on a protected route; role hierarchy enforced; `demo` token can read + run sim but is 403 on a mutating hardware/config/user route.
- audit row written for a mode switch and for a simulation reset; audit has no update/delete route.
- health payload contains the three safety fields; mode defaults to `simulation` on fresh boot.
- protected-band guard: a scheduler forced toward a protected band is redirected and the event is logged.

**Definition of done:** app boots to a login screen; Skip enters a working read-only demo; real users get role-appropriate access; every mutation is audited; mode is a guarded context; full suite green.

---

### STEP 2 — Receive-Only Hardware Layer, Real-Time DSP, Capture & Replay

**Goal:** ingest real spectrum from receive-only SDRs (or recorded files) as a stream of `SweepFrame`s, turn frames into per-band occupancy/SNR the existing schedulers can consume, and record/replay sessions. Sim path untouched.

**Backend**

- `backend/app/models/` additions: `SweepBin`, `SweepFrame` (`ts`, `f_start_hz`, `f_stop_hz`, `bin_hz`, `power_dbm[]`, `source`), `HardwareDevice`, `HardwareStatus`, `HardwareConfig` (`start_freq_hz`, `stop_freq_hz`, `bin_hz`, `sweep_interval_ms`, `gain_db?`, `ppm?`, `source_mode`), `BandObservation`.
- `backend/app/hardware/` package:
  - `base.py` — `HardwareAdapter` ABC: `list_devices()`, `is_available()`, `start_scan(cfg)`, `stop_scan()`, `read_frame() -> SweepFrame | None`, `get_status()`. **No transmit method exists on this class.**
  - `file_replay_adapter.py` — **full.** Reads recorded sweep CSV/JSONL, yields frames at real or accelerated cadence, loops or stops at EOF. This is the default hardware source and the demo path.
  - `rtl_power_adapter.py` — detect `rtl_power` on PATH; spawn it RX-only for the configured range; parse its CSV to `SweepFrame`; clean start/stop; clear error + fall back to `file_replay`/`simulation` if the binary is missing.
  - `hackrf_sweep_adapter.py` — detect `hackrf_sweep`; spawn **`hackrf_sweep` only** (never `hackrf_transfer`); parse its CSV lines to `SweepFrame`; module docstring lists every subprocess arg and asserts RX-only; start/stop; same fallback behaviour.
  - `soapysdr_adapter.py` — **optional, flag-gated.** RX `setupStream(SOAPY_SDR_RX, ...)` / `readStream` only; PSD via Welch to `SweepFrame`. If SoapySDR not importable, adapter reports unavailable.
  - `manager.py` — `HardwareManager` singleton: owns the active adapter + a bounded frame ring buffer + a background reader thread; exposes latest frame, status, and a frame iterator for schedulers.
- `backend/app/dsp/` package (pure NumPy, fully unit-tested):
  - noise-floor estimate (rolling percentile), CFAR-style occupancy per bin, bin→band aggregation onto the configured band grid, per-band SNR estimate, multi-frame exponential smoothing, hop/step detection between frames. Output: `list[BandObservation]` per frame.
- **Live environment adapter:** a thin object implementing the same surface `Simulation` expects from `RFEnvironment`, but sourced from `HardwareManager` + `dsp`. In `live_es` mode `Simulation.step()` pulls the newest `BandObservation` set instead of ground-truth matrices. Ground-truth-only metrics report `n/a` in live mode (see Step 8 metric split).
- **Recording:** `POST /api/hardware/record/start|stop` — persist incoming frames to `backend/data/recordings/<id>/frames.jsonl` + `meta.json` (device, range, bin_hz, start/stop ts, frame count). `GET /api/hardware/recordings`, `GET /api/hardware/recordings/{id}`. Recordings are valid inputs to `file_replay_adapter` and to the Dataset Lab.
- **APIs:** `GET /api/hardware/status`, `GET /api/hardware/devices`, `POST /api/hardware/config` (operator+), `POST /api/hardware/start` (operator+, audited, blocked for `demo`), `POST /api/hardware/stop`, `GET /api/hardware/frame` (latest), `GET /api/hardware/frames?since=` (recent window).

**Frontend**

- New **Hardware Lab** view: source selector (`simulation` / `file_replay` / `rtl_power` / `hackrf_sweep` / `soapysdr`), frequency-range + bin-width + sweep-interval + gain inputs, start/stop, live status panel, a driver/tool-missing error panel with the exact install hint, recording controls + recordings list with "replay this" and "send to Dataset Lab".
- Live Monitor: add a **source-mode badge** and, in live mode, drive the spectrum + waterfall from `/api/hardware/frames`; overlay the scheduler's selected band exactly as in sim.
- All hardware controls disabled with a tooltip for `viewer`/`demo`.

**Tests (`test_ext_step2.py`)**

- `dsp`: synthetic frame with a known tone → correct band flagged active, SNR within tolerance, noise floor sane, hop detected across two frames.
- `file_replay_adapter`: round-trip a written recording → identical frames, correct cadence, clean EOF.
- adapter contract: base class has no `transmit`/`tx`/`start_tx` attribute; `hackrf_sweep_adapter` source contains no `hackrf_transfer`.
- live-mode `Simulation.step()` advances using replayed frames and returns a valid explainability payload.
- `demo` token blocked from `/api/hardware/start`.

**Definition of done:** with no hardware, `file_replay` feeds the exact same dashboard as a live SDR; if `rtl_power`/`hackrf_sweep` exist, frames parse; if not, a specific error shows and sim still runs; recordings replay; no transmit symbol anywhere in `hardware/`.

---

### STEP 3 — Simulation Fidelity, Simulated EW Effects, Scenario Editor, Monte Carlo

**Goal:** make the synthetic environment good enough for defensible research, add *simulated* EW effects as an analysis tool, give analysts a scenario editor, and add batch/statistical evaluation.

**Backend**

- `backend/app/simulation/propagation.py`: free-space + log-distance path loss, configurable terrain/clutter mask per band or per (x,y) grid, multipath fading (Rayleigh/Rician toggle), Doppler shift for moving emitters. All seeded.
- `backend/app/simulation/emitters.py` overhaul → **parametric emitter model**: centre freq + agility (fixed / list-hopping / random-hopping / linear-sweep), PRI model for radar-like (`fixed` / `jitter` / `stagger` / `dwell-switch`), on/off duty model, modulation-class label (`am`, `fm`, `psk`, `fsk`, `chirp`, `noise`, `none` — labels only, no real modulation), ERP, antenna-pattern (omni / sector / rotating with rotation period), threat weight, kinematics (static / waypoint). JSON-serialisable; import/export.
- `backend/app/simulation/ew_effects.py` — **SIMULATION ONLY, cannot import `hardware/`** (enforced by a test): given the ground-truth matrices, apply effect overlays that model an adversary transmitter's impact on *our receiver's observation*:
  - `barrage_noise` (raise noise floor over a range), `spot_jam` (swamp one band), `swept_jam` (moving swamp), `repeater_ghost` (inject a delayed copy of a real emitter into another band), `spoof_track` (add a plausible but fake emitter track).
  - Each effect has start/stop time, frequency extent, power, and a `label` so downstream analysis knows it is synthetic. Effects change `power_db`, `snr_db`, `occupancy_observed`, and a new `is_synthetic_effect` map — they do **not** change `occupancy_truth` (so "detection under jamming" and "was fooled by spoof" become measurable).
- `backend/app/simulation/scenario.py`: a `Scenario` = env config + emitter list + effect list + receiver config + metadata. `POST /api/scenario` (create), `PUT /api/scenario/{id}`, `GET /api/scenario/{id}`, `GET /api/scenario` (list), `POST /api/scenario/{id}/load`, `POST /api/scenario/{id}/duplicate`, export/import JSON. Ship the 6 existing presets re-expressed as `Scenario` files + add **"Jammed Spectrum"** and **"Spoofed Track"** presets. Operator+ to edit; anyone can load.
- `backend/app/comparison/montecarlo.py`: run a scenario across `N` seeds × the scheduler set; return per-metric mean, std, 95% CI, and a win-rate table; cache by `(scenario_id, seed_set, scheduler_set)`. `POST /api/montecarlo/run`, `GET /api/montecarlo/{id}`, export CSV/JSON/HTML.

**Frontend**

- New **Scenario Editor** view: a simple band×time canvas + form panels to add/edit emitters and effects, live mini-preview heatmap, save/load/duplicate/export/import, "load into Live Monitor". Read-only for `viewer`/`demo` (can load, cannot save).
- Strategy Comparison: add a **Monte Carlo** panel — pick scenario, seed count, schedulers → run → table with mean ± CI and a win-rate bar; error bars on the reward/detection charts.
- Live Monitor waterfall: shade cells flagged `is_synthetic_effect`, and add "detection under effect" / "fooled by spoof" counters to the metrics panel.

**Tests (`test_ext_step3.py`)**

- propagation: farther emitter → lower received power, monotonic; Doppler sign correct for approaching vs receding.
- emitter model: stagger PRI produces the expected pulse times; rotating antenna gain peaks once per rotation period.
- `ew_effects`: `spot_jam` raises observed noise in-band and drops observed SNR but leaves `occupancy_truth` untouched; module cannot import `app.hardware` (assert `ImportError` on attempt / static check).
- scenario round-trip: export → import → identical run for a fixed seed.
- Monte Carlo: same seed set → identical aggregates; CI shrinks as N grows.

**Definition of done:** scenarios are editable and portable; simulated jamming/spoofing measurably degrades/deceives the schedulers without touching ground truth or hardware; Monte Carlo gives mean ± CI, not single runs.

---

### STEP 4 — Signal Classification, Emitter/Threat Library, Tasking, Alerting, Anomaly & Forecast

**Goal:** turn raw observations into labelled tracks, match them against an editable (synthetic) library, let an operator task the system, and raise acknowledged alerts.

**Backend**

- `backend/app/analysis/` package:
  - `features.py` — from a band's recent frames: bandwidth estimate, PRI estimate + jitter, hop-rate/pattern, duty cycle, power stats, spectral shape descriptors.
  - `classify.py` — modulation-class + emitter-behaviour classifier. Train a scikit-learn model on **synthetic** labelled data generated from Step 3 emitters (script + fixed seed, model checked in as a small `.joblib`). Always output a probability vector and an explicit `unknown` when max-prob < threshold. Torch CNN on spectrogram is an optional flag-gated upgrade.
  - `tracks.py` — `EmitterTrack`: stitch per-frame band detections into tracks (id, first/last seen, freq behaviour, class + confidence, library match + score, threat). `GET /api/tracks`, `GET /api/tracks/{id}`.
  - `anomaly.py` — unsupervised baseline (per-band power/occupancy distribution over a learning window); flag frames/bands that deviate; `GET /api/anomaly`.
  - `forecast.py` — for periodic tracks, estimate next-activation time and feed a "pre-position" hint into the `priority` and DRL schedulers; `GET /api/forecast`.
- `backend/app/library/` package: `EmitterLibraryEntry` (name, freq range, behaviour params, modulation class, threat, notes, `synthetic: true` always). SQLite-backed, **versioned** (every edit writes a new revision + audit row). CRUD `GET/POST/PUT/DELETE /api/library` (operator+ to write). Matching: score a track against entries by parameter distance; expose top-3 matches + scores. Ship a small **synthetic** starter library.
- `backend/app/tasking/` package: watch lists (bands / freq ranges of interest), priority weights per range, protected bands (from Step 1), and **alert rules** (`new_emitter`, `priority_hit`, `band_change`, `hop_detected`, `anomaly`, `library_match>=score`). `GET/POST /api/tasking/*` (operator+). The scheduler reward/priority inputs read tasking weights.
- `backend/app/alerting/` package: rule evaluation each step/frame → `Alert` (ts, rule, severity, track/band, detail, `state: open|ack|closed`). `GET /api/alerts`, `POST /api/alerts/{id}/ack`, `POST /api/alerts/{id}/close` (analyst+), audited.

**Frontend**

- New **Signals & Tracks** view: live track table (id, freq behaviour, class + confidence, top library match + score, threat, age), click a track → detail with feature values, spectrogram thumbnail, match breakdown, and "add as library entry" (operator+).
- New **Library** view: table + editor + revision history + diff; synthetic-only banner.
- New **Tasking & Alerts** view: watch-list editor, alert-rule builder, live alert feed with ack/close, severity colours; unacked count badge in the top bar.
- Live Monitor: overlay track markers and anomaly shading on the waterfall; forecast "next expected" ticks on the spectrum chart.

**Tests (`test_ext_step4.py`)**

- `features`: synthetic staggered pulse train → PRI + jitter recovered within tolerance; known hopper → hop-rate recovered.
- `classify`: held-out synthetic set → accuracy above a floor; low-SNR blob → `unknown`.
- `tracks`: two-frame gap on same band → one track, not two; frequency step → track updates behaviour, keeps id.
- library matching: a track generated from entry X scores X highest; versioning writes a new revision + audit row; DELETE keeps history.
- alerting: a `new_emitter` rule fires exactly once per new track; ack/close transitions audited; `viewer` cannot ack.

**Definition of done:** observations become classified tracks with confidence and synthetic-library matches; operators can task and get acknowledged alerts; anomaly + forecast feed the scheduler.

---

### STEP 5 — Multi-Node Direction Finding / Geolocation + Map

**Goal:** estimate emitter position from 3+ receive-only nodes, in both simulation (simulated geometry) and live (peer nodes on a LAN), and show it on an offline map.

**Backend**

- `backend/app/df/` package:
  - `nodes.py` — `ReceiverNode` (id, name, lat/lon or local x/y, clock-sync status, last-seen, health). `GET /api/df/nodes`, `POST /api/df/nodes` (operator+). In sim, nodes are placed in the scenario; in live, a node registers via `POST /api/df/register` (LAN only, shared key from config) and pushes per-band bearing/TDOA observations.
  - `tdoa.py` — TDOA multilateration (least-squares + grid refine) with per-node timing-error input → position + covariance → 95 % error ellipse.
  - `aoa.py` — bearing intersection (2+ nodes) → position + ellipse; supports mixing AOA and TDOA.
  - `sync.py` — represent GPSDO/PTP sync quality per node; degrade the ellipse when sync is poor; surface a node-sync dashboard payload.
  - `fusion.py` — combine per-node observations for a track into one geolocation estimate over time (simple EKF or recursive least-squares); output track-position history.
  - APIs: `GET /api/df/fixes`, `GET /api/df/fixes/{track_id}`, `GET /api/df/health`.
- Simulation: extend `Scenario` with node positions + a timing/bearing-noise model so DF works with zero hardware. The RF sim computes true TOA/AOA per node from geometry + propagation, adds noise, feeds the same fusion code as live.
- Metrics: DF accuracy (CEP / RMSE vs truth in sim), ellipse area, node-contribution count.

**Frontend**

- New **Geolocation** view: offline map (bundled raster tiles or a plain coordinate grid fallback — **no online tile fetch**), emitter true position (sim only), estimated position + error ellipse, receiver nodes with sync-status colour, coverage overlay, and a time slider to scrub fix history. Node health/sync table beside the map.
- Live Monitor: small "DF: n nodes, CEP ~x" chip when geolocation is active.

**Tests (`test_ext_step5.py`)**

- TDOA: synthetic 4-node geometry, zero noise → recovered position within 1e-6; with noise → truth inside the 95 % ellipse ≥ 95 % of trials.
- AOA: two clean bearings → correct intersection; parallel bearings → flagged unsolvable, no crash.
- sync degradation: worse timing error → larger ellipse, monotonic.
- fusion: moving emitter → fix history tracks it with bounded lag.
- no network: DF map view builds and renders with tiles absent.

**Definition of done:** in a pure-sim scenario with placed nodes, the platform geolocates emitters with a truthful error ellipse and CEP; the same fusion code accepts live LAN-node observations; the map is fully offline.

---

### STEP 6 — Deep-RL Schedulers, Online Learning, Sim-to-Real, Explainability++

**Goal:** add learning-based schedulers trained in the simulator, let them adapt online in live mode with a safe fallback, and measure (not hand-wave) the sim-to-real gap.

**Backend**

- `backend/app/schedulers/` additions (registry entries): `contextual_bandit` (LinUCB/logistic, no torch), `dqn`, `drqn` (torch, flag-gated, lazy import). Shared feature encoder over the existing compact state + tasking weights + forecast hints.
- `backend/app/rl/` package:
  - `envs.py` — a Gym-style wrapper over `Simulation` for training (vectorisable, seeded).
  - `train.py` — episode loop, replay buffer, target net, checkpointing to `backend/data/rl/`; `POST /api/rl/train` (operator+, async job + progress), `GET /api/rl/jobs`, `GET /api/rl/jobs/{id}`. Learning curves stored and exposed.
  - `curriculum.py` — train across the preset scenarios in increasing difficulty; report per-stage scores.
  - `online.py` — in `live_es` mode, a trained policy may update from the **hardware proxy reward** (from the original hdw design: stable-detection +, rediscovery +, empty-scan −, excess-retune −, under-scan uncertainty bonus; **no ground-truth claims**). A **guardrail**: run `priority` as a shadow baseline; if the online policy's rolling proxy reward drops below the shadow by a margin for a window, auto-revert to `priority` and raise an alert. All transitions audited.
- `backend/app/sim2real/` package:
  - `calibrate.py` — fit the sim's noise-floor, fading, and false-alarm parameters to a chosen recording so the simulator reproduces that environment's statistics; save a calibration profile.
  - `gap.py` — run the same scheduler on (a) the recording via replay and (b) the calibrated sim; report a **reality-gap score** per metric (distribution distance) plus a short automatic narrative.
  - APIs: `POST /api/sim2real/calibrate`, `GET /api/sim2real/profiles`, `POST /api/sim2real/gap`.
- **Explainability++:** extend every decision payload with `counterfactual` (the next-best band and the single factor that would have flipped the choice), and add `GET /api/explain/policy` returning a band×feature attribution grid and, for DQN, a Q-value-per-band vector for the current state.

**Frontend**

- Training Runs view: real training jobs with live learning curves, curriculum stage bars, checkpoint list, "promote checkpoint to active policy" (operator+).
- New **Sim-to-Real** view: pick a recording → calibrate → gap report with per-metric bars and the narrative; profile manager.
- Explainability Log: add a counterfactual column and a policy-attribution heatmap panel; for DQN show the Q-vector as a small bar row per decision.
- Live Monitor: when online learning is active, show a "policy vs shadow" reward strip and a visible "reverted to priority" state if the guardrail trips.

**Tests (`test_ext_step6.py`)**

- `contextual_bandit` beats `random` on ≥1 preset over a fixed seed; runs 1000+ steps without torch installed.
- with torch present: `dqn` trains, learning curve trends up on an easy preset, checkpoint reload reproduces eval score; with torch **absent**: registry still loads, `dqn` selection returns a clear "torch required" error, nothing else breaks.
- online guardrail: inject a deliberately bad policy → auto-revert to `priority` within the window, alert + audit written.
- sim2real `gap`: identical recording vs its own calibrated sim → near-zero gap; a mismatched profile → larger gap, monotonic in the injected mismatch.
- counterfactual: the named flip-factor, when nudged, actually changes the selected band.

**Definition of done:** learning schedulers train in-sim and are selectable; online adaptation in live mode is safe (shadow + auto-revert); the sim-to-real gap is a reported number with a profile behind it; every decision has a counterfactual.

---

### STEP 7 — Streaming, Storage, Data Schema, Security & Air-Gap Hardening, Packaging

**Goal:** make it feel real-time, make the data durable and portable, and make it deployable in a closed facility.

**Backend**

- **Streaming:** add a WebSocket `/ws` channel pushing `state`, `frame`, `decision`, `alert`, `metric` events with sequence numbers and backpressure (drop-oldest for `frame`, never for `alert`). Keep all REST endpoints working. Frontend switches its play loop from polling to `/ws` with automatic reconnect + REST fallback.
- **Storage:** `backend/app/store/` — time-series persistence for frames, observations, decisions, metrics, alerts, tracks, DF fixes to Parquet (pyarrow) partitioned by session/day, with a SQLite index. `Session` object (id, name, tags, mode, scenario, start/stop). `GET /api/sessions`, `GET /api/sessions/{id}`, load a past session read-only into any view. Retention/rotation config.
- **Data schema:** `docs/DATA_SCHEMA.md` — every persisted record with field types, units, and semantics. Versioned (`schema_version` on every record). Export a whole session as one signed `.zip` (Parquet + meta + schema). Import validates against the schema.
- **API versioning:** freeze current paths as `/api/v1/...` with the bare paths aliased; document the deprecation plan.
- **Security hardening:** TLS via config (cert/key paths), per-IP + per-token rate limits, security headers, CORS locked to configured origins, JWT key required (no default in production mode), optional at-rest encryption for `platform.db` and audit/JSONL (key from config/OS keyring), log redaction of tokens. A `--production` flag that refuses to start with any insecure default.
- **Air-gap:** a `scripts/preflight.py` that asserts no outbound socket is opened during a full smoke run; vendored frontend deps; offline font/tiles; no analytics.
- **Packaging:** `Dockerfile` + `docker-compose.yml` (backend, static frontend, no external services), a one-shot `scripts/install_offline.sh` / `.ps1`, a `systemd` unit, and a `/api/health` watchdog with process auto-restart guidance. Frontend served as static build from the backend in production mode.

**Frontend**

- Switch to `/ws` with a connection-status indicator and seamless REST fallback.
- New **Sessions** view: list, filter by tag/mode/date, open read-only, export `.zip`, compare two sessions' metric snapshots side by side.
- Settings view: TLS/rate-limit/retention status (read-only display of effective config for admin).

**Tests (`test_ext_step7.py`)**

- `/ws` delivers ordered events with sequence numbers; a slow client drops `frame`s but never `alert`s; reconnect resumes.
- store round-trip: run a short session → reload from Parquet → decisions/metrics identical; export `.zip` → import → schema-valid, same content.
- `--production` refuses to boot with the default JWT key / no TLS; boots clean with proper config.
- `preflight.py`: full smoke run opens zero outbound connections.
- v1 alias: old paths and `/api/v1/...` return identical payloads.

**Definition of done:** live updates over `/ws`; every run persisted, reloadable, and exportable against a documented schema; starts hardened in production mode; provably air-gapped; ships as a container + offline installer.

---

### STEP 8 — Reporting, Brief Mode, Validation Suite, Docs, Demo Readiness

**Goal:** make the platform present itself, and give a defence reviewer everything needed to trust the numbers.

**Backend**

- `backend/app/reporting.py` overhaul → **mission report** (HTML + print-to-PDF-ready, no external assets): scenario/session summary, timeline, tracks + classifications, DF fixes + CEP, alerts, scheduler-vs-baseline table with mean ± CI, sim-to-real gap, annotated chart snapshots (server-rendered SVG), assumptions, limitations. `GET /api/report/mission/{session_id}` + export.
- **Metric split** finalised and documented in `docs/REFERENCE.md`:
  - *Simulation metrics* (need ground truth): probability of detection, false-alarm rate, interception ratio, average intercept delay, high-priority detection rate, missed-opportunity count, correct-prediction %, **detection-under-effect rate**, **spoof-deception rate**, DF CEP/RMSE.
  - *Live metrics* (no ground truth): occupancy estimate, scan coverage, average observed SNR, revisit time, above-threshold detection count, average proxy reward, recording duration, frame rate, alert counts, policy-vs-shadow margin.
  - Each with a test in `test_ext_step8.py` recomputing it from raw history.
- **Benchmark suite:** `scripts/benchmark.py` — fixed scenarios × fixed seed sets × all schedulers → a JSON report with expected ranges; a `pytest` gate (`test_ext_step8_benchmark.py`) that fails if any headline metric moves outside its tolerance band (regression protection for CI).
- **Ablation runner:** `scripts/ablation.py` — every scheduler vs the two baselines across every preset with 95 % CI → a table for the report.
- **Evidence pack:** `GET /api/evidence/{session_id}` → `.zip` of the session data, the mission report, the benchmark JSON, and a manifest with checksums.

**Frontend**

- **Brief Mode:** a full-screen, keyboard-driven presentation view — big spectrum + waterfall + scan path, the headline before/after numbers (open-loop vs adaptive), and a next/prev step walk-through matching `docs/DEMO.md`. One key toggles it from any view.
- **Before/After** panel on Strategy Comparison: `round_robin` vs the best adaptive scheduler on the loaded scenario, with the three headline deltas called out.
- Reports view: mission-report preview + all exports (report HTML/PDF, session `.zip`, comparison CSV/JSON, evidence pack).

**Docs (rewrite/extend)**

- `README.md` — full platform overview; the two modes; the safety model (receive-only hardware, simulation-only EW effects, no transmit code — with the enforcement points listed); architecture (with-hardware and without); hardware BOM + the receive-only + shielded-lab guidance; every SDR input mode; auth + roles + the Skip button; how to run backend, frontend, tests, benchmark, air-gapped/production; how to use file replay, `rtl_power`, `hackrf_sweep`; the judge demo script; limitations; assumptions log.
- `docs/architecture.md` — updated data-flow for both modes incl. `/ws`, storage, DF, RL.
- `docs/REFERENCE.md` — every new module/class/function + the theory (propagation, CFAR, TDOA/AOA multilateration + covariance, contextual bandits, DQN/DRQN, proxy reward, sim-to-real gap metric, all metric formulas).
- `docs/SECURITY.md` — auth model, roles, audit, air-gap posture, production checklist, data-at-rest options.
- `docs/DATA_SCHEMA.md` — finalised.
- `docs/VALIDATION.md` — benchmark method, ablation results, metric definitions + tests, sim-to-real calibration method, known limitations, HIL (receive-only) test plan + shielded-lab SOP.
- `docs/DEMO.md` — updated 10–12 step script covering: login → Skip → sim baseline → adaptive → Monte Carlo → simulated jamming → tracks/library → tasking/alerts → hardware lab (file replay) → geolocation → sim-to-real → mission report + evidence pack.

**Tests (`test_ext_step8.py` + `test_ext_step8_benchmark.py`)**

- every sim and live metric recomputed from raw history matches the snapshot.
- benchmark gate: headline metrics within tolerance for the fixed seed set.
- mission report renders with zero external asset references (grep the HTML).
- evidence pack manifest checksums verify.
- `docs/` link check: no dead internal links; every new module appears in `REFERENCE.md`.

**Definition of done:** one click produces a defensible mission report and an evidence pack; a CI gate protects the headline numbers; Brief Mode runs the whole story; all docs are judge/reviewer-ready; final response prints every run command (dev, tests, benchmark, air-gapped production).

---

## 6. FINAL ACCEPTANCE CRITERIA (verify in Step 8)

- Fresh clone → offline install → backend + frontend start; login screen appears; **Skip (demo)** enters a working read-only platform.
- Full backend suite green, including every `test_ext_step*` and the benchmark gate.
- **Simulation mode:** high-fidelity scenarios, editable + portable; simulated EW effects measurably degrade/deceive schedulers without altering ground truth; Monte Carlo reports mean ± CI; DF geolocation works with placed nodes and a truthful error ellipse; DRL schedulers train and are selectable; sim-to-real gap is a reported number.
- **Live-ES mode:** `file_replay` drives the identical dashboard as an SDR; `rtl_power` / `hackrf_sweep` parse if present, degrade cleanly if not; recordings replay; online learning is guarded by a shadow baseline with auto-revert.
- **Safety:** `GET /api/health` → `transmit_capability: false`, `hardware_mode: "receive_only"`; no transmit symbol anywhere under `backend/app/hardware/`; `ew_effects` cannot import `hardware/`; all data synthetic; no outbound network in a full smoke run.
- **Platform:** every mutation authed + role-gated + audited; `/ws` live updates with REST fallback; every run persisted, reloadable, exportable against `docs/DATA_SCHEMA.md`; `--production` refuses insecure defaults.
- **Presentation:** mission report + evidence pack export; Brief Mode; before/after headline deltas; all docs updated.
- Final response prints exact commands for: dev backend, dev frontend, tests, benchmark, air-gapped production, and the demo script entry point.

---

## 7. APPENDIX A — CONSOLIDATED NEW DATA MODELS

`User`, `Session (auth)`, `Role`, `AuditRecord`, `ModeState`, `HardwareConfig`, `HardwareDevice`, `HardwareStatus`, `SweepBin`, `SweepFrame`, `BandObservation`, `Recording`, `RecordingMeta`, `PropagationConfig`, `EmitterSpec`, `AntennaPattern`, `Kinematics`, `EWEffectSpec`, `Scenario`, `MonteCarloRun`, `SignalFeatures`, `ModulationClassResult`, `EmitterTrack`, `AnomalyFlag`, `ActivationForecast`, `EmitterLibraryEntry`, `LibraryRevision`, `WatchList`, `AlertRule`, `Alert`, `ReceiverNode`, `NodeSyncStatus`, `DFObservation`, `GeoFix`, `RLJob`, `RLCheckpoint`, `ProxyRewardBreakdown`, `CalibrationProfile`, `RealityGapReport`, `DataRecordEnvelope (schema_version)`, `RunSession`, `MissionReport`, `EvidencePack`.

## 8. APPENDIX B — CONSOLIDATED NEW API MAP

```
auth:        POST /api/auth/login  logout  demo  me  change-password
audit:       GET  /api/audit                                   (operator+)
mode:        GET/POST /api/mode                                 (POST operator+)
hardware:    GET  /api/hardware/status  devices  frame  frames  recordings  recordings/{id}
             POST /api/hardware/config  start  stop  record/start  record/stop   (operator+)
scenario:    GET/POST /api/scenario   GET/PUT /api/scenario/{id}   POST .../load .../duplicate
montecarlo:  POST /api/montecarlo/run    GET /api/montecarlo/{id}   + export
analysis:    GET  /api/tracks  tracks/{id}  anomaly  forecast
library:     GET/POST/PUT/DELETE /api/library                   (write operator+)
tasking:     GET/POST /api/tasking/watchlists  alert-rules  protected-bands   (operator+)
alerts:      GET  /api/alerts    POST /api/alerts/{id}/ack  /close            (analyst+)
df:          GET  /api/df/nodes  fixes  fixes/{track_id}  health
             POST /api/df/nodes  register                       (nodes/operator+)
rl:          POST /api/rl/train   GET /api/rl/jobs  jobs/{id}    (operator+)
sim2real:    POST /api/sim2real/calibrate  gap    GET /api/sim2real/profiles
sessions:    GET  /api/sessions  sessions/{id}   + export .zip
report:      GET  /api/report/mission/{session_id}   /api/evidence/{session_id}
stream:      WS   /ws
health:      GET  /api/health        (unauthenticated)
```
All REST also mounted under `/api/v1/...` from Step 7.

## 9. APPENDIX C — CONFIG KEYS / FEATURE FLAGS

```
SPECTRA_JWT_KEY               (required in --production)
SPECTRA_TOKEN_TTL_HOURS       default 12
SPECTRA_SEED_USERS            default true (dev), false in --production
SPECTRA_DATA_DIR              default backend/data
SPECTRA_CORS_ORIGINS          default http://localhost:5173
SPECTRA_TLS_CERT / _KEY       optional; required by --production
SPECTRA_RATE_LIMIT_RPM        default 600
SPECTRA_DB_ENCRYPTION_KEY     optional at-rest encryption
SPECTRA_PROTECTED_BANDS       default []
SPECTRA_RETENTION_DAYS        default 30
FLAG_SOAPYSDR                 default false
FLAG_TORCH_RL                 default false (auto-off if torch missing)
FLAG_TORCH_CLASSIFIER        default false
FLAG_WS_STREAMING            default true
FLAG_DF                      default true
FLAG_ONLINE_LEARNING        default false (must be enabled per session by operator+)
SPECTRA_DF_NODE_KEY          shared LAN key for node registration
```

---

## 10. WHAT NOT TO DO

- Do not add a transmit path, TX stub, or "future TX" hook anywhere.
- Do not fetch anything over the network at runtime or build time in the shipped artefact.
- Do not replace the hand-built charts with a library unless a step says so.
- Do not delete or weaken existing tests.
- Do not ship real or "realistic-sourced" emitter data — synthetic only, and every library/track record carries `synthetic: true`.
- Do not skip the end-of-step STOP.
