import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  api,
  type ComparisonReport,
  type DatasetMeta,
  type Health,
  type SimState,
} from "./api";

type Conn = "connecting" | "online" | "offline";

const METRIC_LABELS: Array<[keyof SimState["metrics"], string, (v: number) => string]> = [
  ["probability_of_detection", "P(detection)", (v) => v.toFixed(3)],
  ["false_alarm_rate", "False alarm rate", (v) => v.toFixed(3)],
  ["interception_ratio", "Interception ratio", (v) => v.toFixed(3)],
  ["average_intercept_delay", "Avg intercept delay", (v) => `${v.toFixed(1)} slots`],
  ["average_reward", "Avg reward", (v) => v.toFixed(2)],
  ["high_priority_detection_rate", "High-priority det. rate", (v) => v.toFixed(3)],
  ["missed_opportunity_count", "Missed opportunities", (v) => `${v}`],
  ["scan_coverage", "Scan coverage", (v) => v.toFixed(3)],
  ["average_revisit_time", "Avg revisit time", (v) => `${v.toFixed(1)} slots`],
  ["correct_prediction_percentage", "Correct prediction %", (v) => `${v.toFixed(1)}%`],
];

export default function App() {
  const [conn, setConn] = useState<Conn>("connecting");
  const [health, setHealth] = useState<Health | null>(null);
  const [state, setState] = useState<SimState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scheduler, setScheduler] = useState<string>("round_robin");
  const [learners, setLearners] = useState<string[]>([]);
  const [training, setTraining] = useState<string | null>(null);
  const [datasets, setDatasets] = useState<DatasetMeta[]>([]);
  const [comparison, setComparison] = useState<ComparisonReport | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [h, s, sch] = await Promise.all([
        api.health(),
        api.state(),
        api.schedulers(),
      ]);
      setHealth(h);
      setState(s);
      setScheduler(s.scheduler);
      setLearners(sch.learning_schedulers);
      setConn("online");
      setError(null);
    } catch (e) {
      setConn("offline");
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  const loadDatasets = useCallback(async () => {
    try {
      setDatasets((await api.datasetList()).datasets);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    loadDatasets();
  }, [loadDatasets]);

  const runWrapped = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const generateDataset = () =>
    runWrapped(async () => {
      await api.datasetGenerate();
      await loadDatasets();
    });

  const loadDataset = (id: string) =>
    runWrapped(async () => setState(await api.datasetLoad(id, scheduler)));

  const runComparison = () =>
    runWrapped(async () => {
      const set = ["round_robin", "random", "priority", "epsilon_bandit", "ucb_bandit", "q_learning"];
      setComparison(await api.comparisonRun(set, 1000));
    });

  const trainSelected = async () => {
    setBusy(true);
    setError(null);
    setTraining(null);
    try {
      const rep = await api.train(scheduler, 10, 500);
      setTraining(
        `${rep.scheduler}: avg reward ${rep.first_episode_avg_reward.toFixed(1)} → ` +
          `${rep.last_episode_avg_reward.toFixed(1)} ` +
          `(Δ ${rep.reward_improvement >= 0 ? "+" : ""}${rep.reward_improvement.toFixed(1)}, ` +
          `best ep ${rep.best_episode}/${rep.episodes})`,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    refresh();
  }, [refresh]);

  const act = async (fn: () => Promise<SimState>) => {
    setBusy(true);
    setError(null);
    try {
      setState(await fn());
      setConn("online");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setConn("offline");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full flex-col bg-rf-bg text-rf-text">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-rf-border bg-rf-panel px-4 py-2">
        <div className="flex items-baseline gap-3">
          <span className="text-sm font-bold tracking-[0.2em] text-rf-accent">
            SPECTRA-SCAN&nbsp;AI
          </span>
          <span className="text-[11px] text-rf-dim">
            Adaptive Smart Scan Scheduler · Simulated Electronic Support
          </span>
        </div>
        <div className="flex items-center gap-3 text-[11px]">
          <span className="rounded border border-rf-border px-2 py-0.5 text-rf-dim">
            simulation-only · receive-only
          </span>
          <StatusDot conn={conn} />
        </div>
      </header>

      {/* Body: left / center / right */}
      <div className="grid flex-1 grid-cols-[240px_1fr_300px] overflow-hidden">
        {/* Left control panel (placeholder) */}
        <aside className="flex flex-col gap-3 overflow-y-auto border-r border-rf-border bg-rf-panel2 p-3">
          <Panel title="Simulation Control">
            <div className="flex flex-wrap gap-2">
              <Btn disabled={busy} onClick={() => act(() => api.reset())}>
                Reset
              </Btn>
              <Btn disabled={busy} onClick={() => act(() => api.step(1))}>
                Step
              </Btn>
              <Btn disabled={busy} onClick={() => act(() => api.step(25))}>
                +25
              </Btn>
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              <Btn
                disabled={busy}
                onClick={() => act(() => api.run(500, "round_robin"))}
              >
                Run RR ×500
              </Btn>
              <Btn disabled={busy} onClick={() => act(() => api.run(500, "random"))}>
                Run RND ×500
              </Btn>
            </div>
          </Panel>

          <Panel title="Scheduler">
            <select
              value={scheduler}
              onChange={(e) => setScheduler(e.target.value)}
              className="w-full rounded border border-rf-border bg-rf-bg px-1.5 py-1 text-[12px] text-rf-text"
            >
              {(state?.available_schedulers ?? []).map((s) => (
                <option key={s} value={s}>
                  {s}
                  {learners.includes(s) ? "  ⋯learns" : ""}
                </option>
              ))}
            </select>
            <div className="mt-2 flex flex-wrap gap-2">
              <Btn disabled={busy} onClick={() => act(() => api.run(500, scheduler))}>
                Run ×500
              </Btn>
              <Btn disabled={busy} onClick={() => act(() => api.run(1000, scheduler))}>
                Run ×1000
              </Btn>
              <Btn
                disabled={busy || !learners.includes(scheduler)}
                onClick={trainSelected}
              >
                Train ×10
              </Btn>
            </div>
            <div className="mt-1 text-[10px] text-rf-dim">
              active:&nbsp;<span className="text-rf-text">{state?.scheduler ?? "—"}</span>
            </div>
            {training && (
              <p className="mt-2 rounded border border-rf-border bg-rf-bg p-1.5 text-[10px] leading-relaxed text-rf-accent">
                {training}
              </p>
            )}
          </Panel>

          <Panel title="Active decision">
            {state?.last_step ? (
              <DecisionCard step={state.last_step} />
            ) : (
              <Empty>run a step to see the scheduler's reasoning</Empty>
            )}
          </Panel>

          <Panel title="Environment">
            <KV k="bands" v={state?.environment.num_bands} />
            <KV k="time slots" v={state?.environment.num_time_slots} />
            <KV k="emitters" v={state?.environment.emitter_count} />
            <KV
              k="occupancy"
              v={
                state
                  ? `${(state.environment.occupancy_percentage * 100).toFixed(1)}%`
                  : undefined
              }
            />
            <KV k="noise floor" v={state ? `${state.environment.noise_floor_db} dB` : undefined} />
            <KV k="seed" v={state?.environment.seed} />
          </Panel>
        </aside>

        {/* Center: spectrum + waterfall placeholders */}
        <main className="flex flex-col gap-3 overflow-y-auto p-3">
          <Panel title="Spectrum — power vs band (Step 4: live chart)">
            <MiniSpectrum state={state} />
          </Panel>
          <Panel title="Waterfall — band × recent time (Step 4: heatmap)">
            <MiniWaterfall state={state} />
          </Panel>
          <Panel title="Receiver scan path (last decisions)">
            <ScanPath state={state} />
          </Panel>

          <Panel title="Dataset Lab (DeepSense-style synthetic datasets)">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Btn disabled={busy} onClick={generateDataset}>
                Generate from current config
              </Btn>
              <span className="text-[10px] text-rf-dim">
                {state?.replay_mode
                  ? `replaying ${state.dataset_id}`
                  : "live generator"}
              </span>
            </div>
            {datasets.length === 0 ? (
              <Empty>no datasets yet</Empty>
            ) : (
              <table className="w-full text-[11px]">
                <thead className="text-rf-dim">
                  <tr>
                    <th className="text-left font-normal">id</th>
                    <th className="text-right font-normal">bands×slots</th>
                    <th className="text-right font-normal">occ%</th>
                    <th className="text-right font-normal">avg SNR</th>
                    <th />
                  </tr>
                </thead>
                <tbody className="tabular-nums">
                  {datasets.slice(0, 8).map((d) => (
                    <tr key={d.dataset_id} className="border-t border-rf-grid">
                      <td className="text-rf-text">{d.dataset_id}</td>
                      <td className="text-right">
                        {d.number_of_bands}×{d.number_of_time_slots}
                      </td>
                      <td className="text-right">
                        {(d.stats.occupancy_percentage * 100).toFixed(1)}
                      </td>
                      <td className="text-right">{d.stats.average_snr_db.toFixed(1)}</td>
                      <td className="text-right">
                        <button
                          disabled={busy}
                          onClick={() => loadDataset(d.dataset_id)}
                          className="text-rf-scan hover:text-rf-accent disabled:opacity-40"
                        >
                          load
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Panel>

          <Panel title="Strategy Comparison (same scenario, all schedulers)">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Btn disabled={busy} onClick={runComparison}>
                Run comparison ×1000
              </Btn>
              {comparison && (
                <>
                  <span className="text-[11px]">
                    winner:&nbsp;
                    <span className="font-bold text-rf-accent">{comparison.winner}</span>
                  </span>
                  <a
                    href={api.comparisonExportUrl("csv")}
                    className="text-[10px] text-rf-scan hover:text-rf-accent"
                  >
                    ↓ csv
                  </a>
                  <a
                    href={api.comparisonExportUrl("json")}
                    className="text-[10px] text-rf-scan hover:text-rf-accent"
                  >
                    ↓ json
                  </a>
                  <a
                    href={api.comparisonExportUrl("html")}
                    target="_blank"
                    rel="noreferrer"
                    className="text-[10px] text-rf-scan hover:text-rf-accent"
                  >
                    ↗ html
                  </a>
                </>
              )}
            </div>
            {comparison ? (
              <ComparisonTable report={comparison} />
            ) : (
              <Empty>run a comparison to rank strategies</Empty>
            )}
          </Panel>
        </main>

        {/* Right: metrics placeholder */}
        <aside className="flex flex-col gap-3 overflow-y-auto border-l border-rf-border bg-rf-panel2 p-3">
          <Panel title="Metrics">
            {state ? (
              <dl className="space-y-1">
                {METRIC_LABELS.map(([key, label, fmt]) => (
                  <div key={key} className="flex justify-between gap-2">
                    <dt className="text-rf-dim">{label}</dt>
                    <dd className="tabular-nums text-rf-text">
                      {fmt(Number(state.metrics[key]))}
                    </dd>
                  </div>
                ))}
              </dl>
            ) : (
              <Empty>no run yet</Empty>
            )}
          </Panel>

          <Panel title="Receiver">
            <KV k="current band" v={state?.receiver.current_band} />
            <KV k="dwell" v={state ? `${state.receiver.dwell_slots} slot(s)` : undefined} />
            <KV
              k="retune delay"
              v={state ? `${state.receiver.retune_delay_slots} slot(s)` : undefined}
            />
            <KV
              k="det. threshold"
              v={state ? `${state.receiver.detection_threshold_db} dB` : undefined}
            />
            <KV k="total scans" v={state?.receiver.total_scans} />
          </Panel>

          <Panel title="Safety">
            <p className="text-[10px] leading-relaxed text-rf-dim">
              {health?.mode ?? "simulation-only / receive-only"}. No transmission,
              jamming, spoofing, or real emitter libraries. Synthetic spectrum only.
            </p>
          </Panel>
        </aside>
      </div>

      {/* Status bar */}
      <footer className="flex items-center justify-between border-t border-rf-border bg-rf-panel px-4 py-1 text-[11px] text-rf-dim">
        <span>
          {conn === "online" ? "backend online" : conn === "connecting" ? "connecting…" : "backend offline"}
          {error ? ` · ${error}` : ""}
        </span>
        <span>
          t = {state?.time_slot ?? 0} / {state?.max_slots ?? 0}
          {"  ·  "}
          scheduler: {state?.scheduler ?? "—"}
          {busy ? "  ·  working…" : ""}
        </span>
      </footer>
    </div>
  );
}

/* ---------------------------------------------------------------- widgets */

function StatusDot({ conn }: { conn: Conn }) {
  const color =
    conn === "online" ? "bg-rf-accent" : conn === "connecting" ? "bg-rf-warn" : "bg-rf-alert";
  return (
    <span className="flex items-center gap-1">
      <span className={`h-2 w-2 rounded-full ${color}`} />
      <span className="text-rf-dim">{conn}</span>
    </span>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded border border-rf-border bg-rf-panel">
      <div className="border-b border-rf-border px-2 py-1 text-[10px] uppercase tracking-wider text-rf-dim">
        {title}
      </div>
      <div className="p-2 text-[12px]">{children}</div>
    </section>
  );
}

function Btn({
  children,
  onClick,
  disabled,
}: {
  children: ReactNode;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="rounded border border-rf-border bg-rf-panel2 px-2 py-1 text-[11px] text-rf-text transition hover:border-rf-accent hover:text-rf-accent disabled:cursor-not-allowed disabled:opacity-40"
    >
      {children}
    </button>
  );
}

function KV({ k, v }: { k: string; v?: string | number }) {
  return (
    <div className="flex justify-between gap-2">
      <span className="text-rf-dim">{k}</span>
      <span className="tabular-nums text-rf-text">{v ?? "—"}</span>
    </div>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <div className="py-4 text-center text-[11px] text-rf-dim">{children}</div>;
}

function ComparisonTable({ report }: { report: ComparisonReport }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px] text-[11px]">
        <thead className="text-rf-dim">
          <tr>
            <th className="text-left font-normal">#</th>
            <th className="text-left font-normal">scheduler</th>
            <th className="text-right font-normal">score</th>
            <th className="text-right font-normal">P(det)</th>
            <th className="text-right font-normal">intercept</th>
            <th className="text-right font-normal">hi-pri</th>
            <th className="text-right font-normal">delay</th>
            <th className="text-right font-normal">avg R</th>
            <th className="text-right font-normal">missed</th>
            <th className="text-right font-normal">cov</th>
          </tr>
        </thead>
        <tbody className="tabular-nums">
          {report.metrics_table.map((r) => (
            <tr
              key={r.scheduler}
              className={
                "border-t border-rf-grid " +
                (r.scheduler === report.winner ? "text-rf-accent" : "")
              }
            >
              <td>{r.rank}</td>
              <td>{r.scheduler}</td>
              <td className="text-right">{r.weighted_score.toFixed(3)}</td>
              <td className="text-right">{r.probability_of_detection.toFixed(3)}</td>
              <td className="text-right">{r.interception_ratio.toFixed(3)}</td>
              <td className="text-right">{r.high_priority_detection_rate.toFixed(3)}</td>
              <td className="text-right">{r.average_intercept_delay.toFixed(1)}</td>
              <td className="text-right">{r.average_reward.toFixed(2)}</td>
              <td className="text-right">{r.missed_opportunity_count}</td>
              <td className="text-right">{r.scan_coverage.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-1 text-[10px] text-rf-dim">
        seed {report.scenario_seed}
        {report.replayed_dataset ? ` · replay ${report.replayed_dataset}` : ""} ·{" "}
        {report.steps} steps · weighted score:{" "}
        {Object.entries(report.score_weights)
          .map(([k, v]) => `${k.replace(/_/g, " ")} ${v}`)
          .join(", ")}
      </p>
    </div>
  );
}

function DecisionCard({ step }: { step: NonNullable<SimState["last_step"]> }) {
  const d = step.decision;
  const det = step.detection;
  const outcome = det.detected
    ? "hit"
    : det.false_alarm
      ? "false alarm"
      : det.true_active
        ? "miss"
        : "empty";
  const outColor =
    outcome === "hit"
      ? "text-rf-accent"
      : outcome === "false alarm"
        ? "text-rf-alert"
        : "text-rf-dim";
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-rf-dim">t={step.time_slot}</span>
        <span>
          band <span className="text-rf-scan">{d.selected_band}</span> ·{" "}
          <span className={outColor}>{outcome}</span>
        </span>
      </div>
      <div className="flex justify-between text-rf-dim">
        <span>confidence</span>
        <span className="text-rf-text">{(d.confidence * 100).toFixed(0)}%</span>
      </div>
      <div className="flex justify-between text-rf-dim">
        <span>predicted active</span>
        <span className="text-rf-text">
          {d.predicted_active === null ? "—" : d.predicted_active ? "yes" : "no"}
        </span>
      </div>
      <div className="flex justify-between text-rf-dim">
        <span>reward</span>
        <span className={step.reward >= 0 ? "text-rf-accent" : "text-rf-alert"}>
          {step.reward.toFixed(1)}
        </span>
      </div>
      <p className="text-[11px] leading-relaxed text-rf-text">{d.explanation}</p>
      {d.reasons.length > 0 && (
        <ul className="space-y-0.5 text-[10px] text-rf-dim">
          {d.reasons.map((r, i) => (
            <li key={i}>› {r}</li>
          ))}
        </ul>
      )}
      {d.alternatives.length > 0 && (
        <div className="text-[10px] text-rf-dim">
          alternatives: {d.alternatives.join(", ")}
        </div>
      )}
      <div className="text-[10px] text-rf-dim">
        breakdown:{" "}
        {Object.entries(step.reward_breakdown)
          .map(([k, v]) => `${k} ${v}`)
          .join(" · ") || "—"}
      </div>
    </div>
  );
}

function MiniSpectrum({ state }: { state: SimState | null }) {
  if (!state) return <Empty>no data</Empty>;
  const { power_db, active, threshold_db } = state.spectrum;
  const min = Math.min(...power_db, threshold_db) - 2;
  const max = Math.max(...power_db, threshold_db) + 2;
  const h = 120;
  const norm = (p: number) => h - ((p - min) / (max - min)) * h;
  const bw = 100 / power_db.length;
  return (
    <svg viewBox={`0 0 100 ${h}`} preserveAspectRatio="none" className="h-32 w-full">
      <line
        x1={0}
        x2={100}
        y1={norm(threshold_db)}
        y2={norm(threshold_db)}
        stroke="#f0b429"
        strokeWidth={0.4}
        strokeDasharray="1 1"
      />
      {power_db.map((p, i) => (
        <rect
          key={i}
          x={i * bw}
          y={norm(p)}
          width={bw * 0.85}
          height={h - norm(p)}
          fill={
            i === state.receiver.current_band
              ? "#3b82f6"
              : active[i]
                ? "#33d17a"
                : "#1e2a3a"
          }
        />
      ))}
    </svg>
  );
}

function MiniWaterfall({ state }: { state: SimState | null }) {
  if (!state) return <Empty>no data</Empty>;
  const rows = state.waterfall.power_db.slice(-48);
  const all = rows.flat();
  const min = Math.min(...all);
  const max = Math.max(...all) || min + 1;
  return (
    <div className="flex flex-col gap-[1px]">
      {rows.map((row, r) => (
        <div key={r} className="flex gap-[1px]">
          {row.map((p, c) => {
            const t = (p - min) / (max - min);
            const g = Math.round(40 + t * 180);
            return (
              <div
                key={c}
                className="h-[3px] flex-1"
                style={{ background: `rgb(${Math.round(t * 60)}, ${g}, ${Math.round(80 + t * 60)})` }}
              />
            );
          })}
        </div>
      ))}
    </div>
  );
}

function ScanPath({ state }: { state: SimState | null }) {
  if (!state || state.scan_path.length === 0) return <Empty>no scans yet</Empty>;
  const rows = state.scan_path.slice(-12).reverse();
  return (
    <table className="w-full text-[11px]">
      <thead className="text-rf-dim">
        <tr>
          <th className="text-left font-normal">t</th>
          <th className="text-left font-normal">band</th>
          <th className="text-left font-normal">outcome</th>
          <th className="text-right font-normal">reward</th>
        </tr>
      </thead>
      <tbody className="tabular-nums">
        {rows.map((s, i) => (
          <tr key={i} className="border-t border-rf-grid">
            <td>{s.time_slot}</td>
            <td>{s.scanned_band}</td>
            <td
              className={
                s.detected
                  ? "text-rf-accent"
                  : s.false_alarm
                    ? "text-rf-alert"
                    : "text-rf-dim"
              }
            >
              {s.detected ? "hit" : s.false_alarm ? "false alarm" : s.true_active ? "miss" : "empty"}
            </td>
            <td className="text-right">{s.reward.toFixed(1)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
