import { useState } from "react";
import { ALL_SCHEDULERS, api, type ComparisonReport } from "../api";
import { BarChart, LineChart, SERIES_COLORS } from "../charts";
import { Badge, Btn, Empty, Panel } from "../ui";

const DEFAULT = ["round_robin", "random", "priority", "epsilon_bandit", "ucb_bandit", "q_learning"];

export default function StrategyComparison() {
  const [selected, setSelected] = useState<string[]>(DEFAULT);
  const [steps, setSteps] = useState(1000);
  const [report, setReport] = useState<ComparisonReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = (name: string) =>
    setSelected((cur) => (cur.includes(name) ? cur.filter((n) => n !== name) : [...cur, name]));

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      setReport(await api.comparisonRun(selected, steps));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const colorOf = (name: string) =>
    SERIES_COLORS[(report?.ranking.indexOf(name) ?? 0) % SERIES_COLORS.length];

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-2">
      <Panel title="Run comparison — same scenario, every scheduler">
        <div className="flex flex-wrap items-center gap-1.5">
          {ALL_SCHEDULERS.map((n) => (
            <Btn key={n} active={selected.includes(n)} onClick={() => toggle(n)}>
              {n}
            </Btn>
          ))}
          <label className="ml-2 flex items-center gap-1 text-[11px] text-rf-dim">
            steps
            <input
              type="number"
              value={steps}
              step={100}
              min={100}
              max={20000}
              onChange={(e) => setSteps(Number(e.target.value))}
              className="w-20 rounded border border-rf-border bg-rf-bg px-1.5 py-0.5 text-right tabular-nums text-rf-text"
            />
          </label>
          <Btn active onClick={run} disabled={busy || selected.length < 2}>
            {busy ? "running…" : "run comparison"}
          </Btn>
          {report && (
            <span className="ml-2 flex items-center gap-2 text-[11px]">
              winner <Badge tone="good">{report.winner}</Badge>
              <a className="text-rf-scan hover:text-rf-accent" href={api.comparisonExportUrl("csv")}>↓ csv</a>
              <a className="text-rf-scan hover:text-rf-accent" href={api.comparisonExportUrl("json")}>↓ json</a>
              <a className="text-rf-scan hover:text-rf-accent" target="_blank" rel="noreferrer" href={api.comparisonExportUrl("html")}>↗ html</a>
            </span>
          )}
        </div>
        {error && <p className="mt-1 text-[10px] text-rf-alert">{error}</p>}
      </Panel>

      {!report ? (
        <Empty>configure the set and run a comparison</Empty>
      ) : (
        <>
          <Panel title={`Metrics table — seed ${report.scenario_seed}${report.replayed_dataset ? ` · replay ${report.replayed_dataset}` : ""} · ${report.steps} steps`}>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-[11px]">
                <thead className="text-rf-dim">
                  <tr>
                    {["#", "scheduler", "score", "P(det)", "FAR", "intercept", "hi-pri", "delay", "avg R", "missed", "coverage", "correct%"].map((h) => (
                      <th key={h} className={`font-normal ${h === "scheduler" || h === "#" ? "text-left" : "text-right"}`}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="tabular-nums">
                  {report.metrics_table.map((r) => (
                    <tr key={String(r.scheduler)} className={"border-t border-rf-grid " + (r.scheduler === report.winner ? "text-rf-accent" : "")}>
                      <td>{r.rank}</td>
                      <td className="flex items-center gap-1">
                        <span className="inline-block h-2 w-2 rounded-sm" style={{ background: colorOf(String(r.scheduler)) }} />
                        {r.scheduler}
                      </td>
                      <td className="text-right">{Number(r.weighted_score).toFixed(3)}</td>
                      <td className="text-right">{Number(r.probability_of_detection).toFixed(3)}</td>
                      <td className="text-right">{Number(r.false_alarm_rate).toFixed(3)}</td>
                      <td className="text-right">{Number(r.interception_ratio).toFixed(3)}</td>
                      <td className="text-right">{Number(r.high_priority_detection_rate).toFixed(3)}</td>
                      <td className="text-right">{Number(r.average_intercept_delay).toFixed(1)}</td>
                      <td className="text-right">{Number(r.average_reward).toFixed(2)}</td>
                      <td className="text-right">{r.missed_opportunity_count}</td>
                      <td className="text-right">{Number(r.scan_coverage).toFixed(2)}</td>
                      <td className="text-right">{Number(r.correct_prediction_percentage).toFixed(0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-1 text-[10px] text-rf-dim">
              weighted score = {Object.entries(report.score_weights).map(([k, v]) => `${v}·${k.replace(/_/g, " ")}`).join("  +  ")}  (missed / delay inverted)
            </p>
          </Panel>

          <div className="grid grid-cols-2 gap-2">
            <Panel title="Interception ratio">
              <BarChart
                data={report.entries.map((e) => ({ label: e.scheduler, value: e.metrics.interception_ratio, color: colorOf(e.scheduler) }))}
                valueFormat={(v) => v.toFixed(3)}
              />
            </Panel>
            <Panel title="Average reward">
              <BarChart
                data={report.entries.map((e) => ({ label: e.scheduler, value: e.metrics.average_reward, color: colorOf(e.scheduler) }))}
              />
            </Panel>
          </div>

          <Panel title="Reward over time">
            <LineChart
              height={200}
              zeroBaseline
              series={report.entries.map((e) => ({
                name: e.scheduler,
                color: colorOf(e.scheduler),
                points: e.series.average_reward,
                x: e.series.time_slot,
              }))}
            />
          </Panel>
          <Panel title="Detection rate over time">
            <LineChart
              height={200}
              yFormat={(v) => v.toFixed(2)}
              series={report.entries.map((e) => ({
                name: e.scheduler,
                color: colorOf(e.scheduler),
                points: e.series.detection_rate,
                x: e.series.time_slot,
              }))}
            />
          </Panel>
        </>
      )}
    </div>
  );
}
