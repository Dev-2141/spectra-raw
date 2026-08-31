# HDW EXTENSION — DEVELOPER UNDERSTANDING

Companion to [`../hdw extension prompt.md`](../hdw%20extension%20prompt.md).

This document explains **the use of every name** introduced by the extension — each
package, module, class, endpoint, view, and concept: *what it is*, *why it exists*
(how it maps to the real Electronic Support / spectrum-surveillance problem), *what
depends on it*, and *what to say about it in a demo*. Read this before touching the
code so you know what each piece is **for**, not just what it does.

---

## 0. The one idea everything serves

An Electronic Support (ES) receiver has **less instantaneous bandwidth than the
spectrum it must watch**. It can only look at a slice at a time. So something must
continuously decide **where to look next, how long to dwell, and when to come
back**. A fixed sweep is blind to what it just saw; a *smart* scheduler learns
from hits, misses, false alarms, threat, and periodicity and catches far more of
what matters — and can explain every choice.

The original project proved this **in simulation**. The extension makes it a
**dual-mode research platform**: the same scheduler brain now also runs on **real
received spectrum** from a receive-only SDR, adds **direction finding**,
**classification**, **learning schedulers**, **statistical validation**, and the
**access control, audit, and packaging** needed to run it somewhere serious — with
a hard line that **hardware never transmits**.

---

## 1. Safety model — the names that keep it legal and safe

| Name | What it is | Why it exists | Depended on by |
|---|---|---|---|
| **Receive-only** | Hardware adapters expose only RX calls; no transmit method exists on the adapter base class | Transmitting (jamming/spoofing) is illegal without national authorization and can disrupt aviation/GPS/emergency services; it is a weapons domain and out of scope | Every hardware adapter; the health check; the CI grep test |
| **`transmit_capability: false`** | A permanent field in `GET /api/health` | A single, testable, external assertion that the build cannot radiate | Acceptance test; reviewer trust |
| **Simulated EW effects** (`ew_effects.py`) | Code that overlays a jammer/repeater/spoofer's *effect on our observation* onto the synthetic spectrum — numbers in a matrix, never RF | Lets analysts study "can the scheduler still detect under jamming?" and "was it fooled by a spoof track?" without any transmitter | Step 3 scenarios; detection-under-effect and spoof-deception metrics; robustness research |
| **`is_synthetic_effect` map** | Per-cell flag marking spectrum altered by a simulated effect | Keeps ground truth (`occupancy_truth`) honest so "fooled / not fooled" is measurable | Metrics; waterfall shading |
| **Lab reference-signal transmit** | **Documentation only** — shielded/cabled/attenuated setup + receive-side calibration maths | The one legitimate transmit use (calibrating your own receiver) — described so a lab can do it correctly, never implemented here | `docs/VALIDATION.md` HIL plan |
| **`synthetic: true`** | A field on every library entry and track record | Proves no real/classified signal data is present | Library; tracks; exports |
| **Air-gapped** | No outbound network at runtime or in the shipped artefact; `scripts/preflight.py` asserts it | Defence facilities are closed networks; also removes exfiltration and supply-chain surface | Packaging; production mode |

**Rule of thumb for any new code:** if a change could conceivably cause RF to be
emitted, or data to leave the box, it does not belong in this project.

---

## 2. Step 1 names — identity, access, mode

| Name | Use |
|---|---|
| **`auth/` package** | Local username/password login. Turns a single-user demo into something with accountable users. No cloud, no SSO required (SSO is a later hook). |
| **Roles: `viewer < analyst < operator < admin`** | Least-privilege. `viewer` reads; `analyst` acknowledges alerts and runs analysis; `operator` controls hardware, mode, tasking, library, scenarios, training; `admin` manages users and sees the audit log. Every endpoint names its minimum role. |
| **`require_role(min_role)`** | One FastAPI dependency enforcing the hierarchy. The single choke-point for access decisions. |
| **JWT session** | Stateless signed token (12 h). Lets the frontend and any DF node authenticate without a server-side session table. Key comes from config; `--production` refuses the default. |
| **`POST /api/auth/demo` + Skip button** | Issues a credential-free **read-only `viewer`** token with a `demo: true` claim. Purpose: instant walkthrough for a panel with no login friction, while still blocking every mutating/hardware action. The amber "DEMO MODE" banner makes the reduced trust obvious. **Temporary presentation aid — disable in a real deployment.** |
| **`audit/` package, `AuditRecord`** | Append-only log (DB table + daily JSONL) of who did what, when, in which mode. No update/delete path by design. This is what makes "live real-world testing" defensible — every hardware start, mode switch, config and library edit is on record. |
| **`GET /api/audit`** | Admin-only, filterable, exportable view of the above. |
| **`modes/` package, `ModeManager`, `ModeState`** | Makes **Simulation vs Live-ES** a real application state, not a UI toggle. It selects which environment source, reward engine, metric set, and adapters are live. Boots to `simulation` always (safe default). Switching to `live_es` is `operator`+, needs a confirmation token, and is audited. |
| **`config.py`** | One typed settings object (env + defaults). Every tunable and secret lives here, documented in Appendix C of the prompt. No secrets in source. |
| **Protected bands** (`tasking/protected-bands`) | An operator-set "never scan" list (e.g. safety-of-life services). The simulator and the hardware scan loop both override any scheduler choice that lands on a protected band, log it, and note it in the decision explanation. Compliance + safety guardrail. |
| **`LoginScreen`, Admin tab** | The wall and the user/audit management UI. Admin tab is invisible below `admin`. |

**Why Step 1 is first:** every later endpoint must be authed, role-gated, and
audited. Building the spine first means every subsequent feature inherits it
instead of being retrofitted.

---

## 3. Step 2 names — receive-only hardware + DSP + capture

| Name | Use |
|---|---|
| **`SweepFrame` / `SweepBin`** | The universal unit of "spectrum at an instant": a power-vs-frequency vector with metadata. **Every source — sim, file replay, RTL-SDR, HackRF, USRP — produces `SweepFrame`s**, so everything downstream is source-agnostic. |
| **`hardware/base.py` — `HardwareAdapter` ABC** | The common contract (`list_devices / is_available / start_scan / stop_scan / read_frame / get_status`). **Deliberately has no transmit method.** Adding a source = implementing this class. |
| **`file_replay_adapter.py`** | Plays a recorded sweep file back as if it were a live device, at real or accelerated speed. The **default source** and the **demo path**: no SDR needed on stage, no RF-legal risk, fully repeatable. |
| **`rtl_power_adapter.py`** | Wraps the `rtl_power` CLI (RTL-SDR, ~$30). Spawns it RX-only for the configured range, parses its CSV to `SweepFrame`s. The low-cost real-hardware entry point. |
| **`hackrf_sweep_adapter.py`** | Wraps **`hackrf_sweep` only** (HackRF One, wideband RX). Never touches `hackrf_transfer` (the TX tool). Module docstring lists every argument used and asserts RX-only. |
| **`soapysdr_adapter.py`** | Optional, flag-gated generic SDR (USRP etc.) via SoapySDR **RX streaming only** — `readStream`, never `writeStream`. |
| **`hardware/manager.py` — `HardwareManager`** | Owns the active adapter, a background reader thread, and a bounded ring buffer of recent frames. Gives the rest of the app "the latest spectrum" without caring which device produced it. |
| **`dsp/` package** | Turns raw power bins into decisions-ready features: **noise-floor estimate** (rolling percentile), **CFAR occupancy** (is this bin above noise by enough?), **bin→band aggregation** (map fine FFT bins onto the scheduler's coarse band grid), **SNR estimate**, **multi-frame smoothing**, **hop detection**. Pure NumPy, fully unit-tested against synthetic frames. |
| **`BandObservation`** | The DSP output per band per frame: `active?`, `power`, `snr`, `confidence`. This is exactly what a scheduler needs — so in live mode the scheduler consumes `BandObservation`s instead of the sim's ground-truth matrices, **unchanged otherwise**. |
| **Live environment adapter** | A shim that presents `HardwareManager` + `dsp` output through the same interface `Simulation.step()` already expects from `RFEnvironment`. This is the seam that lets one scheduler brain run on both synthetic and real spectrum. |
| **Recording** (`/api/hardware/record/*`, `Recording`, `RecordingMeta`) | Save live frames + metadata to disk. Uses: (1) demo offline later, (2) feed the Dataset Lab, (3) sim-to-real calibration input (Step 6), (4) evidence. |
| **Hardware Lab view** | The operator console: pick source, set frequency range / bin width / sweep interval / gain, start/stop, watch status, see a **specific** error if a CLI tool is missing (with the install hint), manage recordings. |
| **Source-mode badge** | Always-visible chip on Live Monitor: `SIMULATION` / `FILE REPLAY` / `RTL-SDR` / `HACKRF` / `USRP`. The viewer always knows whether they are looking at synthetic or real spectrum. |

**Why it matters:** this is the step that makes the tool "real". After it, the
dashboard you demo in simulation is the *same dashboard* an analyst uses on a live
antenna — only the source badge changes.

---

## 4. Step 3 names — simulation fidelity, EW effects, scenarios, statistics

| Name | Use |
|---|---|
| **`propagation.py`** | Physics the first version skipped: path loss with distance, terrain/clutter masking, multipath fading, Doppler for movers. Makes "the far emitter is harder to hear" and "the mover smears in frequency" true in the sim, so scheduler results transfer better to reality. |
| **`emitters.py` — `EmitterSpec`, `AntennaPattern`, `Kinematics`** | A **parametric** emitter you can fully describe: frequency agility (fixed / list-hop / random-hop / sweep), radar PRI model (fixed / jitter / stagger / dwell-switch), duty cycle, modulation-class *label*, ERP, antenna pattern (omni / sector / rotating), threat weight, motion. This is how you build realistic, varied scenarios instead of six hard-coded ones. |
| **`ew_effects.py` — `EWEffectSpec`** | Simulated adversary transmitters, as **effects on our observation only**: `barrage_noise`, `spot_jam`, `swept_jam`, `repeater_ghost`, `spoof_track`. They change what the receiver *sees* (`power_db`, `snr_db`, `occupancy_observed`) but never `occupancy_truth`, so you can measure "detection under jamming" and "deceived by spoof". **Cannot import `hardware/`** — enforced by a test. |
| **`scenario.py` — `Scenario`** | A saveable, portable bundle: environment + emitters + effects + receiver config + metadata. The unit of "an experiment". Exportable/importable JSON so results are reproducible and shareable. The six original presets become `Scenario` files; "Jammed Spectrum" and "Spoofed Track" are added. |
| **Scenario Editor view** | Build/edit scenarios visually (band×time canvas + forms), preview the heatmap, save/load/duplicate, load straight into Live Monitor. `viewer`/`demo` can load but not save. |
| **`montecarlo.py` — `MonteCarloRun`** | Runs a scenario across **N seeds × all schedulers** and reports **mean, std, 95 % CI, and win-rate** per metric. Replaces "here's one run" with "here's the distribution" — the difference between an anecdote and a result a reviewer accepts. |
| **detection-under-effect rate / spoof-deception rate** | New metrics only meaningful because effects leave ground truth intact: fraction of truly-active band-slots still detected while an effect is active; fraction of decisions driven by a spoofed track. |

---

## 5. Step 4 names — from raw spectrum to labelled tracks

| Name | Use |
|---|---|
| **`analysis/features.py` — `SignalFeatures`** | Per-band descriptors extracted from recent frames: bandwidth, PRI + jitter, hop rate/pattern, duty cycle, power stats, spectral shape. The inputs to classification and library matching. |
| **`analysis/classify.py` — `ModulationClassResult`** | A scikit-learn classifier (trained on **synthetic** data, model checked in) that labels a signal's modulation class and behaviour, always with a probability vector and an explicit **`unknown`** when unsure. Optional torch spectrogram-CNN upgrade behind a flag. Turns "something is in band 17" into "likely a chirped radar, 0.82". |
| **`analysis/tracks.py` — `EmitterTrack`** | Stitches per-frame detections on a band into a persistent track with an id, first/last seen, frequency behaviour, class, library match, threat. The thing an operator actually reasons about. |
| **`analysis/anomaly.py` — `AnomalyFlag`** | Unsupervised baseline of normal per-band power/occupancy; flags deviations. Catches the emitter that does not match any known pattern — "this looks different from ten minutes ago". |
| **`analysis/forecast.py` — `ActivationForecast`** | For periodic tracks, predicts the next activation time and hands the scheduler a "pre-position here" hint. Turns reaction into anticipation for radar-like emitters. |
| **`library/` — `EmitterLibraryEntry`, `LibraryRevision`** | An editable, **versioned** catalogue of (synthetic) emitter signatures. Every edit is a new revision + audit row; delete keeps history. Tracks are scored against it → top-3 matches with scores. This is the "is this one we know?" function, kept unclassified by construction. |
| **`tasking/` — `WatchList`, `AlertRule`** | How an operator directs the system: bands/ranges of interest, priority weights (which feed the scheduler's reward), protected bands, and rules for when to raise an alert (`new_emitter`, `priority_hit`, `band_change`, `hop_detected`, `anomaly`, `library_match>=score`). |
| **`alerting/` — `Alert`** | Rule hits become alerts with severity and an `open → ack → closed` lifecycle. Analyst+ acknowledges/closes; every transition audited. The unacked count sits in the top bar. |
| **Signals & Tracks / Library / Tasking & Alerts views** | The three operator screens for the above: live track table + detail, library editor + revision diff, watch-list/rule builder + live alert feed. |

---

## 6. Step 5 names — direction finding / geolocation

| Name | Use |
|---|---|
| **`df/nodes.py` — `ReceiverNode`, `NodeSyncStatus`** | A networked receive-only sensor with a position and a clock-sync quality. Geolocation needs 3+. In sim they are placed in the scenario; in live they register over the LAN with a shared key and push observations. |
| **`df/tdoa.py`** | **Time Difference of Arrival** multilateration: from when each node heard the signal, solve for position (least-squares + grid refine) with a covariance → a 95 % **error ellipse**. Needs good time sync. |
| **`df/aoa.py`** | **Angle of Arrival**: intersect bearings from 2+ nodes → position + ellipse. Works with poorer timing; can be fused with TDOA. |
| **`df/sync.py`** | Models GPSDO/PTP sync quality per node and **widens the error ellipse when sync is poor** — an honest estimate, not a false pinpoint. |
| **`df/fusion.py` — `GeoFix`** | Combines a track's observations across nodes and over time (recursive least-squares / EKF) into one position estimate with history. Handles movers. |
| **DF metrics — CEP / RMSE, ellipse area** | In simulation you know the true position, so you can report **Circular Error Probable** and RMSE — a real accuracy number, not a claim. |
| **Geolocation view** | Offline map (bundled tiles or a coordinate-grid fallback — **never fetches tiles online**): true position (sim), estimated position + ellipse, nodes coloured by sync status, coverage overlay, time slider over fix history, node-health table. |

**Why it belongs here:** "which band" is scan scheduling; "where is it" is
geolocation. A tool that does both, with a truthful error ellipse, is
substantially more useful than a spectrum display.

---

## 7. Step 6 names — learning schedulers, online adaptation, sim-to-real

| Name | Use |
|---|---|
| **`contextual_bandit` scheduler** | LinUCB/logistic bandit using the full feature vector (state + tasking + forecast). Stronger than the plain bandits, **no torch needed** — keeps the smart path dependency-light. |
| **`dqn` / `drqn` schedulers** | Deep Q-Network / recurrent DQN (PyTorch, flag-gated, lazy import). Learn a scan policy from simulated episodes. If torch is absent they show "torch required" and nothing else breaks. |
| **`rl/envs.py`** | A Gym-style wrapper over `Simulation` so RL libraries can train against it (vectorised, seeded). |
| **`rl/train.py` — `RLJob`, `RLCheckpoint`** | Async training jobs with progress, replay buffer, target network, checkpointing, stored learning curves. `POST /api/rl/train`. |
| **`rl/curriculum.py`** | Trains across the preset scenarios easy→hard and reports per-stage scores — more robust policies, and a story for the report. |
| **`rl/online.py` — `ProxyRewardBreakdown`** | In live mode there is **no ground truth**, so learning uses a **proxy reward**: + for stable above-threshold detection, + for rediscovering an active band, − for empty scans, − for excessive retuning, + uncertainty bonus for under-scanned areas. **It never claims real threat detection.** |
| **Shadow baseline + auto-revert guardrail** | While an online policy adapts, `priority` runs in parallel as a "shadow". If the policy's rolling proxy reward falls below the shadow by a margin for a window, the system **auto-reverts to `priority`** and raises an alert. This is what makes online learning safe to switch on during live testing. |
| **`sim2real/calibrate.py` — `CalibrationProfile`** | Fits the sim's noise floor, fading, and false-alarm parameters to a chosen **recording** so the simulator reproduces that real environment's statistics. |
| **`sim2real/gap.py` — `RealityGapReport`** | Runs the same scheduler on the recording (replay) and on the calibrated sim and reports a **reality-gap score** per metric (distribution distance) plus an auto-written narrative. Turns "does the sim transfer?" into a measured number. |
| **Explainability++ — `counterfactual`, `GET /api/explain/policy`** | Every decision now also says *the single factor that would have changed it* and exposes a band×feature attribution grid (and Q-values per band for DQN). "Band 30 was second; if band 12 weren't stale, it would have won." |

---

## 8. Step 7 names — streaming, storage, schema, hardening, packaging

| Name | Use |
|---|---|
| **`/ws` WebSocket channel** | Pushes `state / frame / decision / alert / metric` events with sequence numbers and backpressure (drop old `frame`s under load, never drop `alert`s). Replaces HTTP polling so the dashboard feels real-time. REST stays as fallback. |
| **`store/` package — Parquet + SQLite index** | Durable time-series persistence of frames, observations, decisions, metrics, alerts, tracks, DF fixes, partitioned by session/day. Nothing is lost when the process stops. |
| **`RunSession` / Sessions view** | Every run is a named, tagged `Session` you can reopen read-only in any view, export as a `.zip`, or compare against another session. |
| **`DataRecordEnvelope` / `schema_version` / `docs/DATA_SCHEMA.md`** | Every persisted record is versioned and documented — field types, units, semantics. Makes the data portable and auditable, and lets future versions migrate cleanly. |
| **`/api/v1/...` alias** | Freezes today's API surface under a versioned path so future changes do not silently break integrations. |
| **`--production` flag** | Refuses to start with any insecure default (default JWT key, no TLS, seed users on). One switch between "easy dev" and "safe deploy". |
| **`scripts/preflight.py`** | Runs a full smoke test and asserts **zero outbound connections** — the air-gap proof. |
| **`Dockerfile` / `docker-compose.yml` / `install_offline.*` / systemd unit** | Ship it as a container or an offline installer with no external services; frontend served static from the backend in production. Deployable on a closed network by someone who is not the author. |
| **At-rest encryption / rate limits / security headers / log redaction** | Standard hardening so "live real-world testing" does not mean "wide open". |

---

## 9. Step 8 names — reporting, validation, presentation

| Name | Use |
|---|---|
| **Mission report** (`/api/report/mission/{session_id}`) | One self-contained HTML/PDF (no external assets): scenario, timeline, tracks + classes, DF fixes + CEP, alerts, scheduler-vs-baseline table with mean ± CI, sim-to-real gap, annotated charts, assumptions, limitations. The artefact you hand a reviewer. |
| **Simulation metrics vs Live metrics split** | Ground-truth metrics (P(detection), false-alarm rate, interception ratio, intercept delay, high-priority rate, missed opportunities, correct-prediction %, detection-under-effect, spoof-deception, DF CEP) only make sense in sim. Live has no truth, so it reports occupancy estimate, coverage, observed SNR, revisit time, above-threshold count, proxy reward, frame rate, alert counts, policy-vs-shadow margin. Each has a test that recomputes it from raw history. |
| **`scripts/benchmark.py` + CI gate** | Fixed scenarios × fixed seeds × all schedulers → a report with **expected ranges**; a pytest gate fails if a headline number drifts out of tolerance. Protects the claims over time. |
| **`scripts/ablation.py`** | Every scheduler vs the two baselines across every preset with 95 % CI — the evidence table that "smart beats open-loop" is real and not cherry-picked. |
| **Evidence pack** (`/api/evidence/{session_id}`) | A `.zip` of session data + mission report + benchmark JSON + a checksum manifest. Reproducibility and provenance in one download. |
| **Brief Mode** | Full-screen, keyboard-driven presentation view: big spectrum + waterfall + scan path, the headline before/after numbers, and a next/prev walk-through matching `docs/DEMO.md`. For the actual pitch. |
| **Before/After panel** | `round_robin` vs the best adaptive scheduler on the loaded scenario with the three headline deltas called out — the core message in one screen. |
| **`docs/` set** (`README`, `architecture`, `REFERENCE`, `SECURITY`, `DATA_SCHEMA`, `VALIDATION`, `DEMO`) | The written record a defence reviewer expects: what it does, how, why the numbers are trustworthy, how it is secured, how to run it, and how to demo it. |

---

## 10. Dependency order (why the steps are in this sequence)

```
Step 1  auth + audit + mode + config      ── everything below is authed/audited/mode-aware
Step 2  hardware + DSP + capture           ── needs mode; gives live SweepFrame/BandObservation
Step 3  sim fidelity + EW + scenarios + MC ── needs nothing from 2; gives Scenario + stats
Step 4  classification + library + tasking ── consumes frames (2) and emitter params (3)
Step 5  direction finding                  ── consumes tracks (4) and scenario geometry (3)
Step 6  DRL + online + sim-to-real         ── trains on sim (3), adapts on live (2), needs tasking (4)
Step 7  streaming + storage + hardening    ── persists everything above; needs auth (1)
Step 8  reporting + validation + docs      ── reports on all of it; needs storage (7)
```

Each step ends with **verify → files changed → known issues → STOP → wait for
`continue step N`**. Do not run ahead.

---

## 11. Quick "what do I say about it" table (for a panel)

| Feature | One sentence |
|---|---|
| Skip / demo login | "Read-only walkthrough with no credentials — disabled in a real deployment." |
| Simulation mode | "High-fidelity synthetic spectrum with propagation, radar PRI models, and *simulated* jamming — no transmitter involved." |
| Live-ES mode | "Same dashboard, fed by a receive-only SDR or a recorded capture — the source badge is the only thing that changes." |
| Adaptive scheduler | "It learns from hits, misses, threat and periodicity, and beats a fixed sweep — with a reason and a counterfactual for every choice." |
| Simulated EW effects | "We can jam or spoof the *simulation* to test whether the scheduler still copes — ground truth is untouched so we can score it." |
| Direction finding | "Three or more receive-only nodes geolocate an emitter with an honest error ellipse and a CEP number." |
| Sim-to-real gap | "We calibrate the simulator to a real capture and report, as a number, how far the two diverge." |
| Monte Carlo + benchmark gate | "Every claim is a distribution over many seeds, and a CI test fails the build if a headline number drifts." |
| Audit + roles + air-gap | "Every action is attributed and logged, access is least-privilege, and nothing talks to the network." |
| Receive-only guarantee | "`/api/health` says `transmit_capability: false`, and a test greps the hardware code to keep it that way." |
