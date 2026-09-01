# SPECTRA-SCAN AI — Judge Demo Script

~8–10 minutes. Backend on `:8000`, frontend on `:5173` (README §6). Everything
shown is **synthetic, receive-only, simulation-only, offline**.

> **Fastest path:** press **`b`** anywhere in the UI for the full-screen
> **Brief Mode** walk-through (← → / space to move, `p` play/pause, `Esc` exit).
> It runs steps 3–12 below on autopilot. The script here is the click-by-click
> version.

---

## 0. Setup (before judges arrive)

```bash
cd backend  && .venv\Scripts\python -m uvicorn app.main:app --port 8000
cd frontend && npm run dev
```

Open `http://localhost:5173`. You land on the **login screen**.

## 1. Login → Skip (demo)

- Click **Skip (demo)**. You enter with a persistent amber
  **DEMO MODE — read-only** banner. Point out: the demo session can *read
  everything and run the simulation* but is blocked from every mutation
  (hardware, config, users, library, scenarios).
- (Optional) instead use a dev **"enter as operator"** quick-login button to show
  the write paths. Header shows the user chip, the **SIM / LIVE-ES** mode toggle,
  and the persistent **SIMULATION** / **RECEIVE-ONLY** safety chip.

## 2. Orient

Left = simulation controls + scenario presets. Centre = spectrum + waterfall.
Right = live metrics + the active-decision explanation. Header shows the
connection state (`live ⇅` when `/ws` is connected, `polling` on fallback).

## 3. Open-loop baseline

- Sidebar → **Scheduler** = `round_robin` → **apply & reset** → **▶ play**
  (speed ~5/tick).
- Right panel: **missed opportunities** climbs fast, **avg reward** sits deeply
  negative, **interception ratio** is low. The blue scan-path line in the
  waterfall marches straight past the bright (active) columns.
- **❚❚ pause.**

## 4. Adaptive scheduler

- Scheduler = `priority` → **apply & reset** → **▶ play**.
- **P(detection)** and **interception ratio** rise; **avg reward** climbs toward
  0; the scan path clusters on active / high-threat bands. The **Active
  decision** panel shows *why* each band was chosen — confidence, top factors
  (`activity`, `hit_rate`, `threat`, `periodicity`), alternatives, a
  **counterfactual**, and the reward breakdown. Pause.

## 5. Strategy comparison + before/after

- Sidebar → **Scenario presets** → **Periodic Radar-Like Challenge**.
- Top nav → **Strategy Comparison** → **run comparison**.
- `priority` wins with a large average-reward margin. The **Before / after**
  panel calls out three headline deltas (avg reward, interception ratio, missed
  opportunities) for `round_robin` → best adaptive.
- Scroll to the **Monte Carlo** panel → pick the scenario, ~12 seeds → **run** →
  mean ± 95 % CI table + win-rate bar. "An anecdote becomes a result."

## 6. Simulated jamming

- Top nav → **Scenario Editor** → load the **Jammed Spectrum** preset (or add a
  `spot_jam` effect) → **load into Live Monitor**.
- On **Live Monitor**, the waterfall shades cells flagged `is_synthetic_effect`;
  the metrics panel adds **detection-under-effect** and **fooled-by-spoof**
  counters. Ground truth is untouched — the effect degrades the *observation*
  only.

## 7. Signals & tracks, library

- Top nav → **Signals & Tracks**: the live track table (id, freq behaviour,
  class + confidence, top library match + score, threat, age). Click a track →
  feature values, spectrogram thumbnail, match breakdown.
- Top nav → **Library**: synthetic starter entries, revision history + diff,
  "synthetic-only" banner. Every edit writes a new revision + an audit row.

## 8. Tasking & alerts

- Top nav → **Tasking & Alerts**: add a watch list over a band range, add a
  `new_emitter` alert rule → the live alert feed fills; ack / close an alert. The
  unacked count shows as a badge on the tab.

## 9. Hardware lab (file replay)

- Top nav → **Hardware Lab**: source selector. Pick **file_replay**, choose a
  bundled recording → **start**. The live status panel shows frame rate; the
  Live Monitor now runs from `/api/hardware/frames` with a **source-mode badge**.
- Point out: if `rtl_power` / `hackrf_sweep` were on `PATH` they would parse
  here; missing, you get the exact install hint and the sim still runs. **No
  transmit control exists anywhere on this screen.**

## 10. Geolocation

- Top nav → **Geolocation**: an offline map (or coordinate-grid fallback), the
  emitter true position (sim only), the estimated position + **95 % error
  ellipse**, receiver nodes coloured by sync quality, a time slider to scrub fix
  history. The Live Monitor shows a "DF: n nodes, CEP ~x" chip.

## 11. Sim-to-real gap

- Top nav → **Sim-to-Real**: pick a recording → **calibrate** → a
  `CalibrationProfile` is saved → **gap report** with per-metric bars and a short
  narrative. The reality gap is a *number with a profile behind it*.

## 12. Mission report + evidence pack

- Top nav → **Sessions**: start recording, run ~200 steps, finish. (Or use a
  session already recorded.)
- Top nav → **Reports** → **Mission report & evidence pack** → pick the session →
  **build mission report**. You get the summary, the **simulation vs live metric
  split**, a **scheduler-vs-baseline table with mean ± CI**, timeline, tracks, DF
  fixes, alerts, assumptions, limitations.
- **↗ html** opens the self-contained report (hand-built SVG charts, zero
  external assets). **↓ evidence .zip** downloads the pack: raw session + report
  + a fresh benchmark JSON + a SHA-256 manifest a reviewer can verify offline.
- The **Metric definitions** panel below lists every metric and which mode it
  applies to.

---

## One-line takeaway

> An ES receiver can only look at one band at a time. A fixed sweep misses most
> of the spectrum; a scheduler that learns from hits, misses, threat and
> periodicity catches far more of what matters — in simulation *and* from a
> receive-only SDR — and every decision, metric and run is explainable,
> reproducible, auditable, and produced fully offline.

## CI / reviewer commands

```bash
cd backend
.venv\Scripts\python -m pytest -q                 # full suite incl. every test_ext_step*
.venv\Scripts\python -m scripts.benchmark         # headline-metric CI gate
.venv\Scripts\python -m scripts.ablation          # every scheduler vs baselines, 95% CI
.venv\Scripts\python -m scripts.preflight         # proves zero outbound connections
```
