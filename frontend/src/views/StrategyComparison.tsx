import { useEffect, useState } from "react";
import {
  ALL_SCHEDULERS,
  api,
  type ComparisonReport,
  type MonteCarloReport,
  type Scenario,
} from "../api";
import { BarChart, LineChart, SERIES_COLORS } from "../charts";
import { Badge, Btn, Empty, ErrorBanner, Loading, Panel } from "../ui";

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
        {error && (
          <div className="mt-1">
            <ErrorBanner message={error} onRetry={run} />
          </div>
        )}
      </Panel>

      {busy && !report ? (
        <Loading label={`running ${selected.length} schedulers × ${steps} steps…`} />
      ) : !report ? (
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

      <MonteCarloPanel schedulers={selected} />
    </div>
  );
}

// --------------------------------------------------------------------------- //
function MonteCarloPanel({ schedulers }: { schedulers: string[] }) {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = useState<string>("");
  const [nSeeds, setNSeeds] = useState(12);
  const [steps, setSteps] = useState(600);
  const [rep, setRep] = useState<MonteCarloReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api
      .scenarios()
      .then((r) => setScenarios(r.scenarios))
      .catch(() => undefined);
  }, []);

  const run = async () => {
    setBusy(true);
    setErr(null);
    try {
      setRep(
        await api.montecarloRun({
          scenario_id: scenarioId || null,
          schedulers,
          n_seeds: nSeeds,
          steps,
        }),
      );
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  const rewardAgg = (schName: string) =>
    rep?.entries
      .find((e) => e.scheduler === schName)
      ?.aggregates.find((a) => a.metric === "average_reward");

  return (
    <Panel title="Monte Carlo — N seeds × schedulers, mean ± 95% CI">
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-1 text-[11px] text-rf-dim">
          scenario
          <select
            value={scenarioId}
            onChange={(e) => setScenarioId(e.target.value)}
            className="rounded border border-rf-border bg-rf-bg px-1.5 py-1 text-[11px] text-rf-text"
          >
            <option value="">current config</option>
            {scenarios.map((s) => (
              <option key={s.scenario_id} value={s.scenario_id}>
                {s.name}
                {s.effects.length ? ` (${s.effects.length} fx)` : ""}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1 text-[11px] text-rf-dim">
          seeds
          <input
            type="number"
            min={2}
            max={200}
            value={nSeeds}
            onChange={(e) => setNSeeds(Number(e.target.value))}
            className="w-16 rounded border border-rf-border bg-rf-bg px-1.5 py-0.5 text-right tabular-nums text-rf-text"
          />
        </label>
        <label className="flex items-center gap-1 text-[11px] text-rf-dim">
          steps
          <input
            type="number"
            min={50}
            step={100}
            value={steps}
            onChange={(e) => setSteps(Number(e.target.value))}
            className="w-20 rounded border border-rf-border bg-rf-bg px-1.5 py-0.5 text-right tabular-nums text-rf-text"
          />
        </label>
        <Btn active onClick={run} disabled={busy || schedulers.length < 2}>
          {busy ? "running…" : "run monte carlo"}
        </Btn>
        {rep && (
          <span className="flex items-center gap-2 text-[11px]">
            winner <Badge tone="good">{rep.winner}</Badge>
            <a
              className="text-rf-scan hover:text-rf-accent"
              href={api.montecarloExportUrl(rep.montecarlo_id, "csv")}
            >
              ↓ csv
            </a>
            <a
              className="text-rf-scan hover:text-rf-accent"
              target="_blank"
              rel="noreferrer"
              href={api.montecarloExportUrl(rep.montecarlo_id, "html")}
            >
              ↗ html
            </a>
          </span>
        )}
      </div>

      {err && (
        <div className="mt-1">
          <ErrorBanner message={err} onRetry={run} />
        </div>
      )}

      {busy && !rep ? (
        <Loading label={`${nSeeds} seeds × ${schedulers.length} schedulers…`} />
      ) : !rep ? (
        <p className="mt-2 text-[11px] text-rf-dim">
          Runs each scheduler across {nSeeds} seeds and reports the distribution
          of every metric — an anecdote becomes a result.
        </p>
      ) : (
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[560px] text-[11px] tabular-nums">
            <thead className="text-rf-dim">
              <tr>
                {["scheduler", "avg reward (mean ± CI)", "win rate", "P(det)", "intercept", "missed"].map(
                  (h) => (
                    <th
                      key={h}
                      className={"font-normal " + (h === "scheduler" ? "text-left" : "text-right")}
                    >
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {rep.ranking.map((name) => {
                const e = rep.entries.find((x) => x.scheduler === name)!;
                const get = (m: string) => e.aggregates.find((a) => a.metric === m);
                const r = rewardAgg(name)!;
                return (
                  <tr
                    key={name}
                    className={
                      "border-t border-rf-grid " +
                      (name === rep.winner ? "text-rf-accent" : "")
                    }
                  >
                    <td>{name}</td>
                    <td className="text-right">
                      {r.mean.toFixed(2)}{" "}
                      <span className="text-rf-dim">
                        [{r.ci95_low.toFixed(2)}, {r.ci95_high.toFixed(2)}]
                      </span>
                    </td>
                    <td className="text-right">{(e.win_rate * 100).toFixed(0)}%</td>
                    <td className="text-right">
                      {get("probability_of_detection")?.mean.toFixed(3)}
                    </td>
                    <td className="text-right">
                      {get("interception_ratio")?.mean.toFixed(3)}
                    </td>
                    <td className="text-right">
                      {get("missed_opportunity_count")?.mean.toFixed(0)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="mt-2">
            <BarChart
              data={rep.ranking.map((n, i) => ({
                label: `${n} (${((rep.entries.find((e) => e.scheduler === n)?.win_rate ?? 0) * 100).toFixed(0)}%)`,
                value: rep.entries.find((e) => e.scheduler === n)?.win_rate ?? 0,
                color: SERIES_COLORS[i % SERIES_COLORS.length],
              }))}
              valueFormat={(v) => `${(v * 100).toFixed(0)}%`}
            />
          </div>
        </div>
      )}
    </Panel>
  );
}
