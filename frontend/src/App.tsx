import { useEffect, useMemo, useState } from "react";
import { api, type PlatformMode } from "./api";
import { useAuth } from "./auth";
import ControlSidebar from "./ControlSidebar";
import { LoadingBar } from "./ui";
import { useSim } from "./useSim";
import Admin from "./views/Admin";
import BriefMode from "./views/BriefMode";
import DatasetLab from "./views/DatasetLab";
import ExplainabilityLog from "./views/ExplainabilityLog";
import Geolocation from "./views/Geolocation";
import HardwareLab from "./views/HardwareLab";
import Library from "./views/Library";
import LiveMonitor from "./views/LiveMonitor";
import Reports from "./views/Reports";
import ScenarioEditor from "./views/ScenarioEditor";
import Sessions from "./views/Sessions";
import SignalsTracks from "./views/SignalsTracks";
import Sim2Real from "./views/Sim2Real";
import StrategyComparison from "./views/StrategyComparison";
import TaskingAlerts from "./views/TaskingAlerts";
import TrainingRuns from "./views/TrainingRuns";

const BASE_TABS = [
  "Live Monitor",
  "Hardware Lab",
  "Scenario Editor",
  "Signals & Tracks",
  "Geolocation",
  "Library",
  "Tasking & Alerts",
  "Strategy Comparison",
  "Dataset Lab",
  "Training Runs",
  "Sim-to-Real",
  "Sessions",
  "Explainability Log",
  "Reports",
] as const;
type Tab = (typeof BASE_TABS)[number] | "Admin";
const NO_SIDEBAR: Tab[] = [
  "Admin",
  "Hardware Lab",
  "Scenario Editor",
  "Signals & Tracks",
  "Geolocation",
  "Library",
  "Tasking & Alerts",
  "Sessions",
  "Sim-to-Real",
];

export default function App() {
  const sim = useSim();
  const { session, hasRole, logout } = useAuth();
  const [tab, setTab] = useState<Tab>("Live Monitor");
  const [mode, setMode] = useState<PlatformMode | null>(null);
  const [switching, setSwitching] = useState(false);
  const [hwSource, setHwSource] = useState<string | null>(null);
  const [brief, setBrief] = useState(false);
  const s = sim.state;

  // `b` from any view toggles Brief Mode (ignored while typing in a field).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "b" || e.metaKey || e.ctrlKey || e.altKey) return;
      const el = e.target as HTMLElement | null;
      if (el && ["INPUT", "SELECT", "TEXTAREA"].includes(el.tagName)) return;
      setBrief((v) => !v);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const isAdmin = hasRole("admin");
  const canSwitchMode = hasRole("operator");
  const tabs = useMemo<Tab[]>(
    () => (isAdmin ? [...BASE_TABS, "Admin"] : [...BASE_TABS]),
    [isAdmin],
  );

  useEffect(() => {
    api.getMode().then(setMode).catch(() => undefined);
  }, []);

  // Keep the local mode in sync with whatever the sim state reports.
  useEffect(() => {
    if (s?.platform) setMode(s.platform);
  }, [s?.platform]);

  // While in live mode, surface which receive-only source is feeding the app.
  useEffect(() => {
    if (mode?.mode !== "live_es") {
      setHwSource(null);
      return;
    }
    let stop = false;
    const tick = () =>
      api
        .hwStatus()
        .then((st) => {
          if (!stop) setHwSource(st.running ? st.source_mode : "no source");
        })
        .catch(() => undefined);
    tick();
    const id = window.setInterval(tick, 3000);
    return () => {
      stop = true;
      window.clearInterval(id);
    };
  }, [mode?.mode]);

  async function switchMode(next: "simulation" | "live_es") {
    if (!canSwitchMode || switching || mode?.mode === next) return;
    if (
      !window.confirm(
        next === "live_es"
          ? "Switch to LIVE-ES mode? The receiver path is receive-only. Continue?"
          : "Switch back to SIMULATION mode?",
      )
    )
      return;
    setSwitching(true);
    try {
      setMode(await api.setMode(next));
    } catch (e) {
      window.alert(String(e));
    } finally {
      setSwitching(false);
    }
  }

  const live = mode?.mode === "live_es";

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

        <nav className="flex flex-wrap gap-1">
          {tabs.map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={
                "relative rounded px-2 py-1 text-[11px] transition " +
                (t === tab
                  ? "bg-rf-accent/15 text-rf-accent"
                  : "text-rf-dim hover:text-rf-text")
              }
            >
              {t}
              {t === "Tasking & Alerts" && !!s?.unacked_alerts && (
                <span className="ml-1 rounded bg-rf-alert px-1 text-[9px] text-rf-bg">
                  {s.unacked_alerts}
                </span>
              )}
            </button>
          ))}
        </nav>

        <div className="flex items-center gap-2 text-[10px]">
          {/* brief mode */}
          <button
            onClick={() => setBrief(true)}
            title="full-screen walk-through (press b)"
            className="rounded border border-rf-border px-1.5 py-0.5 text-rf-dim hover:border-rf-accent hover:text-rf-accent"
          >
            ▶ Brief
          </button>

          {/* mode switch */}
          <div className="flex overflow-hidden rounded border border-rf-border">
            {(["simulation", "live_es"] as const).map((m) => (
              <button
                key={m}
                onClick={() => switchMode(m)}
                disabled={!canSwitchMode || switching}
                title={
                  canSwitchMode
                    ? `switch to ${m}`
                    : "requires operator role"
                }
                className={
                  "px-1.5 py-0.5 transition disabled:cursor-not-allowed " +
                  (mode?.mode === m
                    ? "bg-rf-accent/15 text-rf-accent"
                    : "text-rf-dim hover:text-rf-text disabled:hover:text-rf-dim")
                }
              >
                {m === "simulation" ? "SIM" : "LIVE-ES"}
              </button>
            ))}
          </div>

          {/* receive-only / simulation safety chip */}
          <span
            className={
              "rounded border px-1.5 py-0.5 " +
              (live
                ? "border-rf-warn/50 text-rf-warn"
                : "border-rf-accent/40 text-rf-accent")
            }
            title={live ? `receive-only source: ${hwSource ?? "…"}` : undefined}
          >
            {live
              ? `RECEIVE-ONLY${hwSource ? ` · ${hwSource}` : ""}`
              : "SIMULATION"}
          </span>

          {/* connection */}
          <span
            className="flex items-center gap-1.5"
            title={
              sim.streaming
                ? "live updates over /ws"
                : sim.connected
                  ? "connected — polling (ws fallback)"
                  : "offline"
            }
          >
            <span
              className={
                "h-2 w-2 rounded-full " +
                (sim.streaming
                  ? "bg-rf-accent"
                  : sim.connected
                    ? "bg-rf-warn"
                    : "bg-rf-alert")
              }
            />
            <span className="text-rf-dim">
              {sim.streaming ? "live ⇅" : sim.connected ? "polling" : "offline"}
            </span>
          </span>

          {/* user chip */}
          {session && (
            <span className="flex items-center gap-1.5 border-l border-rf-border pl-2">
              <span className="text-rf-text">{session.username}</span>
              <span className="text-rf-dim">· {session.role}</span>
              <button
                onClick={logout}
                className="rounded border border-rf-border px-1.5 py-0.5 text-rf-dim hover:border-rf-accent hover:text-rf-accent"
              >
                sign out
              </button>
            </span>
          )}
        </div>
      </header>

      {session?.demo && (
        <div className="shrink-0 bg-rf-warn/15 px-3 py-1 text-center text-[10px] text-rf-warn">
          DEMO MODE — read-only, simulation only, not for operational use
        </div>
      )}
      {live && mode?.degraded && (
        <div className="shrink-0 bg-rf-warn/10 px-3 py-1 text-center text-[10px] text-rf-warn">
          LIVE-ES selected but no hardware configured — running degraded (hardware
          layer arrives in extension Step 2)
        </div>
      )}

      <LoadingBar visible={sim.busy} />

      <div className="flex min-h-0 flex-1">
        {!NO_SIDEBAR.includes(tab) && <ControlSidebar sim={sim} />}
        <main className="flex min-h-0 flex-1 flex-col">
          {tab === "Live Monitor" && <LiveMonitor sim={sim} />}
          {tab === "Hardware Lab" && <HardwareLab />}
          {tab === "Scenario Editor" && <ScenarioEditor />}
          {tab === "Signals & Tracks" && <SignalsTracks />}
          {tab === "Geolocation" && <Geolocation />}
          {tab === "Library" && <Library />}
          {tab === "Tasking & Alerts" && <TaskingAlerts />}
          {tab === "Strategy Comparison" && <StrategyComparison />}
          {tab === "Dataset Lab" && <DatasetLab sim={sim} />}
          {tab === "Training Runs" && <TrainingRuns />}
          {tab === "Sim-to-Real" && <Sim2Real />}
          {tab === "Sessions" && <Sessions />}
          {tab === "Explainability Log" && <ExplainabilityLog />}
          {tab === "Reports" && <Reports />}
          {tab === "Admin" && isAdmin && <Admin />}
        </main>
      </div>

      <footer className="flex shrink-0 items-center justify-between border-t border-rf-border bg-rf-panel px-3 py-1 text-[10px] text-rf-dim">
        <span>
          {s
            ? `${s.environment.num_bands} bands · ${s.environment.emitter_count} emitters · occ ${(s.environment.occupancy_percentage * 100).toFixed(1)}% · noise ${s.environment.noise_floor_db} dB · seed ${s.environment.seed}`
            : "—"}
          {s?.preset ? `  ·  scenario: ${s.preset}` : ""}
          {s?.protected_bands && s.protected_bands.length
            ? `  ·  protected: ${s.protected_bands.join(",")}`
            : ""}
          {sim.error ? `  ·  ${sim.error}` : ""}
        </span>
        <span>
          t = {s?.time_slot ?? 0} / {s?.max_slots ?? 0}
          {"  ·  "}
          {s?.scheduler ?? "—"}
          {s?.replay_mode ? "  ·  replay" : ""}
          {sim.busy ? "  ·  working…" : sim.playing ? "  ·  playing" : ""}
          {live ? "  ·  live-es / receive-only" : "  ·  simulation-only / receive-only"}
        </span>
      </footer>

      {brief && <BriefMode sim={sim} onExit={() => setBrief(false)} />}
    </div>
  );
}
