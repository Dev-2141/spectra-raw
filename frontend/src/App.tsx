import { useState } from "react";
import ControlSidebar from "./ControlSidebar";
import { useSim } from "./useSim";
import LiveMonitor from "./views/LiveMonitor";
import StrategyComparison from "./views/StrategyComparison";
import DatasetLab from "./views/DatasetLab";
import TrainingRuns from "./views/TrainingRuns";
import ExplainabilityLog from "./views/ExplainabilityLog";
import Reports from "./views/Reports";

const TABS = [
  "Live Monitor",
  "Strategy Comparison",
  "Dataset Lab",
  "Training Runs",
  "Explainability Log",
  "Reports",
] as const;
type Tab = (typeof TABS)[number];

export default function App() {
  const sim = useSim();
  const [tab, setTab] = useState<Tab>("Live Monitor");
  const s = sim.state;

  return (
    <div className="flex h-full flex-col bg-rf-bg text-rf-text">
      <header className="flex shrink-0 items-center justify-between border-b border-rf-border bg-rf-panel px-3 py-1.5">
        <div className="flex items-baseline gap-3">
          <span className="text-[13px] font-bold tracking-[0.22em] text-rf-accent">
            SPECTRA-SCAN&nbsp;AI
          </span>
          <span className="hidden text-[10px] text-rf-dim sm:inline">
            Adaptive Smart Scan Scheduler · Simulated Electronic Support
          </span>
        </div>
        <nav className="flex gap-1">
          {TABS.map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={
                "rounded px-2 py-1 text-[11px] transition " +
                (t === tab
                  ? "bg-rf-accent/15 text-rf-accent"
                  : "text-rf-dim hover:text-rf-text")
              }
            >
              {t}
            </button>
          ))}
        </nav>
        <span className="flex items-center gap-1.5 text-[10px]">
          <span
            className={
              "h-2 w-2 rounded-full " +
              (sim.connected ? "bg-rf-accent" : "bg-rf-alert")
            }
          />
          <span className="text-rf-dim">
            {sim.connected ? "backend online" : "offline"}
          </span>
        </span>
      </header>

      <div className="flex min-h-0 flex-1">
        <ControlSidebar sim={sim} />
        <main className="flex min-h-0 flex-1 flex-col">
          {tab === "Live Monitor" && <LiveMonitor sim={sim} />}
          {tab === "Strategy Comparison" && <StrategyComparison />}
          {tab === "Dataset Lab" && <DatasetLab sim={sim} />}
          {tab === "Training Runs" && <TrainingRuns />}
          {tab === "Explainability Log" && <ExplainabilityLog />}
          {tab === "Reports" && <Reports />}
        </main>
      </div>

      <footer className="flex shrink-0 items-center justify-between border-t border-rf-border bg-rf-panel px-3 py-1 text-[10px] text-rf-dim">
        <span>
          {s
            ? `${s.environment.num_bands} bands · ${s.environment.emitter_count} emitters · occ ${(s.environment.occupancy_percentage * 100).toFixed(1)}% · noise ${s.environment.noise_floor_db} dB · seed ${s.environment.seed}`
            : "—"}
          {sim.error ? `  ·  ${sim.error}` : ""}
        </span>
        <span>
          t = {s?.time_slot ?? 0} / {s?.max_slots ?? 0}
          {"  ·  "}
          {s?.scheduler ?? "—"}
          {s?.replay_mode ? "  ·  replay" : ""}
          {sim.busy ? "  ·  working…" : sim.playing ? "  ·  playing" : ""}
          {"  ·  simulation-only / receive-only"}
        </span>
      </footer>
    </div>
  );
}
