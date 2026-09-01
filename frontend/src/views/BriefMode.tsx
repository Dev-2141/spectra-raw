import { useCallback, useEffect, useRef, useState } from "react";
import { api, type ComparisonReport } from "../api";
import { SpectrumChart, Waterfall } from "../charts";
import type { SimControls } from "../useSim";

// Full-screen, keyboard-driven walk-through that mirrors docs/DEMO.md.
// One key (`b` from any view) toggles it; arrows / space advance; Esc exits.

type Slide = {
  id: string;
  title: string;
  note: string;
  visual?: "spectrum" | "waterfall" | "beforeafter" | null;
  onEnter?: (sim: SimControls) => void;
};

const SLIDES: Slide[] = [
  {
    id: "title",
    title: "SPECTRA-SCAN AI",
    note:
      "Adaptive, explainable scan scheduling for simulated electronic support. " +
      "Receive-only hardware path, simulation-only EW effects, no transmit code, " +
      "no outbound network. Everything shown is synthetic.",
  },
  {
    id: "problem",
    title: "The problem",
    note:
      "An ES receiver can look at exactly one band at a time. A fixed linear " +
      "sweep spends the same dwell on empty spectrum as on the band that matters, " +
      "so it misses most short, hopping and high-threat emissions.",
  },
  {
    id: "baseline",
    title: "1 · Open-loop baseline (round_robin)",
    note:
      "Reset to the periodic radar-like scenario and let a fixed sweep run. " +
      "Watch missed-opportunity count climb and average reward sit deeply " +
      "negative — the scan path marches straight past the bright columns.",
    visual: "waterfall",
    onEnter: (sim) => {
      void sim
        .reset({ preset: "Periodic Radar-Like Challenge", scheduler: "round_robin" })
        .then(() => sim.play());
    },
  },
  {
    id: "adaptive",
    title: "2 · Adaptive scheduler (priority)",
    note:
      "Same scenario, same seed — only the policy changes. The priority " +
      "scheduler predicts the next emission from period and threat and parks the " +
      "receiver on the band before it fires. Detection and interception rise; " +
      "average reward climbs toward zero.",
    visual: "waterfall",
    onEnter: (sim) => {
      void sim
        .reset({ preset: "Periodic Radar-Like Challenge", scheduler: "priority" })
        .then(() => sim.play());
    },
  },
  {
    id: "spectrum",
    title: "3 · Every decision is explainable",
    note:
      "The active decision carries a confidence, the top three factors " +
      "(activity, hit-rate, threat, periodicity), the alternatives it rejected, " +
      "a counterfactual, and the full reward breakdown.",
    visual: "spectrum",
  },
  {
    id: "beforeafter",
    title: "4 · Before / after",
    note:
      "round_robin vs priority on the loaded scenario. Three headline deltas: " +
      "average reward, interception ratio, missed opportunities.",
    visual: "beforeafter",
  },
  {
    id: "montecarlo",
    title: "5 · Monte Carlo — an anecdote becomes a result",
    note:
      "Strategy Comparison → Monte Carlo runs every scheduler across N seeds and " +
      "reports mean ± 95% confidence interval and a win-rate table. The benchmark " +
      "and ablation runners freeze this into a CI gate.",
  },
  {
    id: "jamming",
    title: "6 · Simulated EW effects",
    note:
      "Barrage / spot / swept jamming, repeater ghosts and spoof tracks modify " +
      "the observed spectrum only — never occupancy_truth. So detection-under-" +
      "jamming and spoof-deception rate become measurable numbers, and this " +
      "subsystem cannot import the hardware layer.",
  },
  {
    id: "tracks",
    title: "7 · Tracks, library, tasking & alerts",
    note:
      "Observations become classified emitter tracks with confidence, matched " +
      "against a synthetic library (versioned, every edit audited). Operators set " +
      "watch lists and alert rules; alerts are acknowledged and closed.",
  },
  {
    id: "hardware",
    title: "8 · Hardware lab & geolocation",
    note:
      "file_replay feeds the identical dashboard as a live SDR; rtl_power / " +
      "hackrf_sweep parse if present and degrade cleanly if not. 3+ receive-only " +
      "nodes give a TDOA / AOA fix with a truthful error ellipse — on an offline " +
      "map, no tile fetch.",
  },
  {
    id: "sim2real",
    title: "9 · Sim-to-real gap",
    note:
      "Calibrate the simulator's noise floor, fading and false-alarm rate to a " +
      "recording, then score the distribution distance per metric — the reality " +
      "gap is a reported number with a profile behind it, not a hand-wave.",
  },
  {
    id: "report",
    title: "10 · Mission report & evidence pack",
    note:
      "One click produces a self-contained mission report (summary, metric split, " +
      "scheduler-vs-baseline with CI, tracks, DF, alerts, assumptions, limits) and " +
      "an evidence pack: raw session + report + benchmark JSON + SHA-256 manifest.",
  },
  {
    id: "takeaway",
    title: "Takeaway",
    note:
      "A fixed sweep misses most of the spectrum. A scheduler that learns from " +
      "hits, misses, threat and periodicity catches far more of what matters — " +
      "and every decision it makes is explainable, reproducible and auditable.",
  },
];

export default function BriefMode({
  sim,
  onExit,
}: {
  sim: SimControls;
  onExit: () => void;
}) {
  const [i, setI] = useState(0);
  const [cmp, setCmp] = useState<ComparisonReport | null>(null);
  const [cmpErr, setCmpErr] = useState<string | null>(null);
  const entered = useRef<Set<string>>(new Set());

  const slide = SLIDES[i];
  const next = useCallback(() => setI((v) => Math.min(SLIDES.length - 1, v + 1)), []);
  const prev = useCallback(() => setI((v) => Math.max(0, v - 1)), []);

  // headline before/after numbers — fetched once
  useEffect(() => {
    api
      .comparisonRun(["round_robin", "priority"], 800)
      .then(setCmp)
      .catch((e) => setCmpErr(e instanceof Error ? e.message : String(e)));
  }, []);

  // fire a slide's onEnter action exactly once per entry
  useEffect(() => {
    if (slide.onEnter && !entered.current.has(slide.id)) {
      entered.current.add(slide.id);
      slide.onEnter(sim);
    }
    if (!slide.visual || slide.visual === "beforeafter") sim.pause();
  }, [slide, sim]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        sim.pause();
        onExit();
      } else if (["ArrowRight", " ", "PageDown"].includes(e.key)) {
        e.preventDefault();
        next();
      } else if (["ArrowLeft", "PageUp"].includes(e.key)) {
        e.preventDefault();
        prev();
      } else if (e.key === "p") {
        sim.playing ? sim.pause() : sim.play();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [next, prev, onExit, sim]);

  const s = sim.state;

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-rf-bg text-rf-text">
      <header className="flex shrink-0 items-center justify-between border-b border-rf-border bg-rf-panel px-4 py-2">
        <span className="text-[12px] font-bold tracking-[0.22em] text-rf-accent">
          BRIEF MODE
        </span>
        <span className="text-[10px] text-rf-dim">
          ← → / space to move · p play/pause · Esc exit
        </span>
        <button
          onClick={() => {
            sim.pause();
            onExit();
          }}
          className="rounded border border-rf-border px-2 py-0.5 text-[10px] text-rf-dim hover:border-rf-accent hover:text-rf-accent"
        >
          exit
        </button>
      </header>

      <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-6 px-8 py-6">
        <div className="w-full max-w-5xl">
          <div className="text-[11px] uppercase tracking-[0.3em] text-rf-dim">
            {i === 0 ? "SIH prototype" : `step ${i} of ${SLIDES.length - 1}`}
          </div>
          <h1 className="mt-1 text-3xl font-semibold text-rf-text">{slide.title}</h1>
          <p className="mt-3 max-w-3xl text-[15px] leading-relaxed text-rf-dim">
            {slide.note}
          </p>
        </div>

        <div className="flex w-full max-w-5xl min-h-[280px] items-center justify-center">
          {slide.visual === "spectrum" && s && (
            <div className="w-full rounded border border-rf-border bg-rf-panel p-3">
              <div className="mb-1 text-[10px] uppercase tracking-wider text-rf-dim">
                spectrum — t {s.time_slot} · {s.scheduler}
              </div>
              <div className="h-[220px]">
                <SpectrumChart
                  power={s.spectrum.power_db}
                  active={s.spectrum.active}
                  threshold={s.spectrum.threshold_db}
                  currentBand={s.receiver.current_band}
                  height={220}
                />
              </div>
            </div>
          )}

          {slide.visual === "waterfall" && s && (
            <div className="w-full rounded border border-rf-border bg-rf-panel p-3">
              <div className="mb-1 flex items-center justify-between text-[10px] uppercase tracking-wider text-rf-dim">
                <span>
                  waterfall + scan path — {s.scheduler} · t {s.time_slot}/{s.max_slots}
                </span>
                <span className="tabular-nums normal-case text-rf-text">
                  avg R {s.metrics.average_reward.toFixed(2)} · intercept{" "}
                  {s.metrics.interception_ratio.toFixed(3)} · missed{" "}
                  {s.metrics.missed_opportunity_count}
                </span>
              </div>
              <Waterfall
                power={s.waterfall.power_db}
                startSlot={s.waterfall.start_slot}
                scanPath={s.scan_path}
                height={240}
              />
            </div>
          )}

          {slide.visual === "beforeafter" && (
            <BeforeAfter cmp={cmp} err={cmpErr} />
          )}
        </div>
      </div>

      <footer className="flex shrink-0 items-center justify-center gap-1.5 border-t border-rf-border bg-rf-panel px-4 py-2">
        {SLIDES.map((sl, idx) => (
          <button
            key={sl.id}
            onClick={() => setI(idx)}
            title={sl.title}
            className={
              "h-1.5 rounded-full transition-all " +
              (idx === i ? "w-6 bg-rf-accent" : "w-1.5 bg-rf-border hover:bg-rf-dim")
            }
          />
        ))}
      </footer>
    </div>
  );
}

function BeforeAfter({
  cmp,
  err,
}: {
  cmp: ComparisonReport | null;
  err: string | null;
}) {
  if (err)
    return <p className="text-[12px] text-rf-alert">comparison failed: {err}</p>;
  if (!cmp)
    return <p className="text-[12px] text-rf-dim">running round_robin vs priority…</p>;

  const e = (n: string) => cmp.entries.find((x) => x.scheduler === n)?.metrics;
  const b = e("round_robin");
  const a = e("priority");
  if (!b || !a) return <p className="text-[12px] text-rf-dim">no data</p>;

  const rows = [
    {
      label: "average reward",
      before: b.average_reward,
      after: a.average_reward,
      fmt: (v: number) => v.toFixed(2),
      up: true,
    },
    {
      label: "interception ratio",
      before: b.interception_ratio,
      after: a.interception_ratio,
      fmt: (v: number) => v.toFixed(3),
      up: true,
    },
    {
      label: "missed opportunities",
      before: b.missed_opportunity_count,
      after: a.missed_opportunity_count,
      fmt: (v: number) => v.toFixed(0),
      up: false,
    },
  ];

  return (
    <div className="grid w-full gap-4 sm:grid-cols-3">
      {rows.map((r) => {
        const delta = r.after - r.before;
        const improved = r.up ? delta > 0 : delta < 0;
        return (
          <div
            key={r.label}
            className="rounded border border-rf-border bg-rf-panel p-4 text-center"
          >
            <div className="text-[10px] uppercase tracking-wider text-rf-dim">
              {r.label}
            </div>
            <div className="mt-2 text-[13px] text-rf-dim line-through">
              {r.fmt(r.before)}
            </div>
            <div className="text-3xl font-semibold text-rf-text">
              {r.fmt(r.after)}
            </div>
            <div
              className={
                "mt-1 text-[12px] tabular-nums " +
                (improved ? "text-rf-accent" : "text-rf-alert")
              }
            >
              {delta >= 0 ? "+" : ""}
              {r.fmt(delta)} {improved ? "better" : "worse"}
            </div>
          </div>
        );
      })}
      <p className="col-span-full text-center text-[10px] text-rf-dim">
        seed {cmp.scenario_seed} · {cmp.steps} steps · same scenario, only the
        policy changes
      </p>
    </div>
  );
}
