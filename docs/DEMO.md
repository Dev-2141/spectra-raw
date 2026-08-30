# SPECTRA-SCAN AI — Judge Demo Script

~5 minutes. Assumes backend on `:8000` and frontend on `:5173` (see README §8–9).
Everything shown is synthetic, receive-only, simulation-only.

---

## 0. Setup (before the judges arrive)

```bash
cd backend  && .venv\Scripts\python -m uvicorn app.main:app --port 8000
cd frontend && npm run dev
```

Open `http://localhost:5173`. You land on the **Live Monitor** tab with a
persistent control sidebar on the left.

---

## 1. Open the dashboard

Point out the layout: left = simulation controls + scenario presets; centre =
spectrum + waterfall; right = live metrics + active-decision explanation; bottom
= event log + reward timeline. Status bar shows `simulation-only / receive-only`.

## 2. Start the round-robin baseline

- Sidebar → **Scheduler** dropdown → `round_robin`.
- Click **apply & reset**.
- Click **▶ play** (speed slider ~5/tick).

## 3. Show the missed opportunities

While it plays, on the right panel:

- **missed opps** climbs quickly.
- **avg reward** stays deeply negative.
- **interception ratio** is low.

In the centre, the **waterfall** shows bright (active) cells that the blue
scan-path line marches straight past.

Click **❚❚ pause**.

## 4. Switch to the priority scheduler

- Scheduler dropdown → `priority`.
- **apply & reset** → **▶ play**.

## 5. Show improved detection

- **P(detection)** and **interception ratio** rise; **avg reward** climbs toward 0.
- The scan path now clusters on active / high-threat bands instead of sweeping.
- Right panel **Active decision** shows *why* each band was chosen (confidence,
  top factors like `activity`, `hit_rate`, `threat`, `periodicity`, alternatives,
  reward breakdown).

Pause.

## 6. Run the strategy comparison

- Sidebar → **Scenario presets** → **Periodic Radar-Like Challenge**
  (the sidebar description explains it; config fields update to bands 48, seed
  4404, threshold 7).
- Top nav → **Strategy Comparison** tab.
- Leave the scheduler set as-is, click **run comparison**.
- Result: **`priority` wins** with a large average-reward margin (~−0.6 vs ~−18
  for both baselines). Point at the **Reward over time** and **Detection rate
  over time** line charts and the **winner** badge.
- (Optional) toggle in `q_learning` / `ucb_bandit` and re-run.

## 7. Show the heatmap and scan path

- Top nav → **Live Monitor**.
- Centre → **Waterfall — band × recent time (scan path overlaid)**. The legend:
  green = hit, amber = miss, red = false alarm, blue = empty. On the periodic
  preset you can see the regular pulse columns and the scheduler parking on them.

## 8. Open the explainability log

- Top nav → **Explainability Log**.
- Live-updating table: `t`, scheduler, band, confidence, prediction, outcome,
  reward, explanation + top-factor chips + alternatives.
- Click the **hit** filter to show only successful intercepts.

## 9. Generate a dataset

- Top nav → **Dataset Lab**.
- Left form → **generate** (or pick a preset first, then generate).
- Click the new dataset in the list → right panel shows stats
  (occupancy %, sparsity, active bands, SNR, threat split, emitter-type mix) and
  a **preview heatmap**.
- Click **load into simulation** → a `replay` badge appears in the sidebar; the
  Live Monitor now runs that exact saved scenario.

## 10. Export a report

- Top nav → **Reports**.
- **Current run report**: metric grid + recent decisions. Click **↓ csv**,
  **↓ json**, or **↗ html**.
- **Last strategy comparison**: ranked table with the same export links.

---

## One-line takeaway

> An ES receiver can only look at one band at a time. A fixed sweep misses most of
> the spectrum; a scheduler that learns from hits, misses, threat and periodicity
> catches far more of what matters — and every decision it makes is explainable.
