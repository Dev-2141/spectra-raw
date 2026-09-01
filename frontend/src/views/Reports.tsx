import { useCallback, useEffect, useState } from "react";
import {
  api,
  downloadAuthed,
  openAuthed,
  type ComparisonReport,
  type MetricSplit,
  type MissionReport,
  type RunReport,
  type SessionRow,
} from "../api";
import { Badge, Btn, Empty, ErrorBanner, Loading, Panel, Stat } from "../ui";

export default function Reports() {
  const [run, setRun] = useState<RunReport | null>(null);
  const [cmp, setCmp] = useState<ComparisonReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setRun(await api.runReport());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    try {
      setCmp(await api.comparisonLast());
    } catch {
      setCmp(null);
    }
  }, []);
  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-2">
      <Panel
        title="Current run report"
        right={
          <span className="flex gap-2 text-[10px]">
            <a className="text-rf-scan hover:text-rf-accent" href={api.runReportExportUrl("csv")}>↓ csv</a>
            <a className="text-rf-scan hover:text-rf-accent" href={api.runReportExportUrl("json")}>↓ json</a>
            <a className="text-rf-scan hover:text-rf-accent" target="_blank" rel="noreferrer" href={api.runReportExportUrl("html")}>↗ html</a>
            <button className="text-rf-dim hover:text-rf-text" onClick={refresh}>refresh</button>
          </span>
        }
      >
        {!run ? (
          error ? (
            <ErrorBanner message={error} onRetry={refresh} />
          ) : (
            <Loading />
          )
        ) : (
          <div className="space-y-2">
            <div className="flex flex-wrap gap-1.5 text-[10px] text-rf-dim">
              <Badge>{run.generated_at}</Badge>
              <Badge tone="scan">{run.scheduler}</Badge>
              {run.preset && <Badge tone="good">{run.preset}</Badge>}
              {run.replay_mode && <Badge tone="warn">replay {run.dataset_id}</Badge>}
              <Badge>
                {run.environment_config.num_bands} bands · seed {run.environment_config.seed}
              </Badge>
              <Badge>
                t {run.time_slot}/{run.max_slots} · {run.steps_run} steps
              </Badge>
              <Badge>
                thr {run.receiver_config.detection_threshold_db} dB · dwell {run.receiver_config.dwell_slots} · retune{" "}
                {run.receiver_config.retune_delay_slots}
              </Badge>
            </div>
            <div className="grid grid-cols-3 gap-1.5 md:grid-cols-5">
              <Stat label="P(det)" value={run.metrics.probability_of_detection.toFixed(3)} tone="good" />
              <Stat label="FAR" value={run.metrics.false_alarm_rate.toFixed(3)} />
              <Stat label="interception" value={run.metrics.interception_ratio.toFixed(3)} />
              <Stat label="avg reward" value={run.metrics.average_reward.toFixed(2)} tone={run.metrics.average_reward >= 0 ? "good" : "bad"} />
              <Stat label="hi-pri det." value={run.metrics.high_priority_detection_rate.toFixed(3)} tone="warn" />
              <Stat label="coverage" value={run.metrics.scan_coverage.toFixed(3)} />
              <Stat label="missed" value={run.metrics.missed_opportunity_count} tone="bad" />
              <Stat label="intercept delay" value={run.metrics.average_intercept_delay.toFixed(1)} />
              <Stat label="revisit" value={run.metrics.average_revisit_time.toFixed(1)} />
              <Stat label="correct %" value={run.metrics.correct_prediction_percentage.toFixed(0)} />
            </div>
          </div>
        )}
      </Panel>

      <Panel title="Recent decisions in this run">
        {run && run.recent_decisions.length > 0 ? (
          <table className="w-full text-[11px]">
            <thead className="text-rf-dim">
              <tr>
                <th className="text-left font-normal">t</th>
                <th className="px-2 text-right font-normal">band</th>
                <th className="text-left font-normal">outcome</th>
                <th className="px-2 text-right font-normal">reward</th>
                <th className="pl-3 text-left font-normal">explanation</th>
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {run.recent_decisions
                .slice()
                .reverse()
                .map((d, i) => (
                  <tr key={i} className="border-t border-rf-grid">
                    <td>{d.time_slot}</td>
                    <td className="px-2 text-right text-rf-scan">{d.selected_band}</td>
                    <td>{d.outcome}</td>
                    <td className={`px-2 text-right ${d.reward >= 0 ? "text-rf-accent" : "text-rf-alert"}`}>{d.reward.toFixed(1)}</td>
                    <td className="whitespace-normal pl-3 text-rf-text">{d.explanation}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        ) : (
          <Empty>no decisions yet</Empty>
        )}
      </Panel>

      <Panel
        title="Last strategy comparison"
        right={
          cmp && (
            <span className="flex gap-2 text-[10px]">
              <a className="text-rf-scan hover:text-rf-accent" href={api.comparisonExportUrl("csv")}>↓ csv</a>
              <a className="text-rf-scan hover:text-rf-accent" href={api.comparisonExportUrl("json")}>↓ json</a>
              <a className="text-rf-scan hover:text-rf-accent" target="_blank" rel="noreferrer" href={api.comparisonExportUrl("html")}>↗ html</a>
            </span>
          )
        }
      >
        {!cmp ? (
          <Empty>run a comparison in the Strategy Comparison tab</Empty>
        ) : (
          <div className="space-y-1">
            <div className="flex flex-wrap gap-1.5 text-[10px] text-rf-dim">
              <Badge tone="good">winner {cmp.winner}</Badge>
              <Badge>seed {cmp.scenario_seed}</Badge>
              <Badge>{cmp.steps} steps</Badge>
              {cmp.replayed_dataset && <Badge tone="warn">replay {cmp.replayed_dataset}</Badge>}
            </div>
            <table className="w-full text-[11px]">
              <thead className="text-rf-dim">
                <tr>
                  <th className="text-left font-normal">#</th>
                  <th className="text-left font-normal">scheduler</th>
                  <th className="text-right font-normal">score</th>
                  <th className="text-right font-normal">avg R</th>
                  <th className="text-right font-normal">intercept</th>
                  <th className="text-right font-normal">missed</th>
                </tr>
              </thead>
              <tbody className="tabular-nums">
                {cmp.metrics_table.map((r) => (
                  <tr key={String(r.scheduler)} className={"border-t border-rf-grid " + (r.scheduler === cmp.winner ? "text-rf-accent" : "")}>
                    <td>{r.rank}</td>
                    <td>{r.scheduler}</td>
                    <td className="text-right">{Number(r.weighted_score).toFixed(3)}</td>
                    <td className="text-right">{Number(r.average_reward).toFixed(2)}</td>
                    <td className="text-right">{Number(r.interception_ratio).toFixed(3)}</td>
                    <td className="text-right">{r.missed_opportunity_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <MissionReportPanel />
      <MetricDefsPanel />
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Mission report + evidence pack (Step 8)
// --------------------------------------------------------------------------- //
function MissionReportPanel() {
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [sid, setSid] = useState<string>("");
  const [report, setReport] = useState<MissionReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadSessions = useCallback(async () => {
    try {
      const rows = (await api.sessions()).sessions;
      setSessions(rows);
      setSid((cur) => cur || rows[0]?.session_id || "");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);
  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  const build = useCallback(async () => {
    if (!sid) return;
    setBusy(true);
    setError(null);
    try {
      setReport(await api.missionReport(sid));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setReport(null);
    } finally {
      setBusy(false);
    }
  }, [sid]);

  const b = report?.scheduler_vs_baseline ?? null;

  return (
    <Panel
      title="Mission report & evidence pack"
      right={
        <span className="flex items-center gap-2 text-[10px]">
          <button className="text-rf-dim hover:text-rf-text" onClick={loadSessions}>
            reload sessions
          </button>
        </span>
      }
    >
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-1 text-[11px] text-rf-dim">
          session
          <select
            value={sid}
            onChange={(e) => setSid(e.target.value)}
            className="rounded border border-rf-border bg-rf-bg px-1.5 py-1 text-[11px] text-rf-text"
          >
            {sessions.length === 0 && <option value="">no recorded sessions</option>}
            {sessions.map((s) => (
              <option key={s.session_id} value={s.session_id}>
                {s.name} · {s.mode} · {s.scheduler || "—"} ·{" "}
                {s.row_counts?.decisions ?? 0} steps
              </option>
            ))}
          </select>
        </label>
        <Btn active onClick={build} disabled={!sid || busy}>
          {busy ? "building…" : "build mission report"}
        </Btn>
        {report && (
          <span className="flex items-center gap-2 text-[10px]">
            <button
              className="text-rf-scan hover:text-rf-accent"
              onClick={() => openAuthed(api.missionReportExportUrl(sid, "html"))}
            >
              ↗ html
            </button>
            <button
              className="text-rf-scan hover:text-rf-accent"
              onClick={() =>
                downloadAuthed(
                  api.missionReportExportUrl(sid, "json"),
                  `mission_${sid}.json`,
                )
              }
            >
              ↓ json
            </button>
            <button
              className="text-rf-scan hover:text-rf-accent"
              onClick={() =>
                downloadAuthed(api.evidencePackUrl(sid), `evidence_${sid}.zip`)
              }
            >
              ↓ evidence .zip
            </button>
          </span>
        )}
      </div>

      {error && (
        <div className="mt-1">
          <ErrorBanner message={error} onRetry={build} />
        </div>
      )}

      {!report ? (
        <p className="mt-2 text-[11px] text-rf-dim">
          Pick a recorded session (Sessions tab → start/finish recording) and
          build a self-contained mission report: summary, the simulation-vs-live
          metric split, a scheduler-vs-baseline table with mean ± CI, timeline,
          tracks, DF fixes, alerts, assumptions and limitations. The evidence
          pack bundles the raw session, the report, a fresh benchmark JSON and a
          SHA-256 manifest.
        </p>
      ) : (
        <div className="mt-2 space-y-2">
          <div className="flex flex-wrap gap-1.5 text-[10px] text-rf-dim">
            <Badge>{report.session.session_id}</Badge>
            <Badge tone="scan">{report.session.scheduler || "—"}</Badge>
            <Badge tone={report.metrics.mode_applicability === "ground_truth" ? "good" : "warn"}>
              {report.metrics.mode_applicability}
            </Badge>
            <Badge>{report.summary.steps} steps</Badge>
            <Badge>{report.session.scenario || "—"}</Badge>
          </div>
          <div className="grid grid-cols-3 gap-1.5 md:grid-cols-5">
            <Stat label="detections" value={report.summary.detections} tone="good" />
            <Stat label="false alarms" value={report.summary.false_alarms} tone="bad" />
            <Stat
              label="avg reward"
              value={report.summary.average_reward.toFixed(2)}
              tone={report.summary.average_reward >= 0 ? "good" : "bad"}
            />
            <Stat label="alerts" value={report.alerts.total} tone="warn" />
            <Stat label="DF fixes" value={report.df_fixes.n} />
          </div>

          {b && (
            <div>
              <div className="mb-1 text-[10px] uppercase tracking-wider text-rf-dim">
                scheduler vs baseline — {b.scenario} · seeds {b.seeds.join(", ")} ·{" "}
                {b.steps} steps · winner{" "}
                <span className="text-rf-accent">{b.winner}</span>
              </div>
              <table className="w-full text-[11px] tabular-nums">
                <thead className="text-rf-dim">
                  <tr>
                    <th className="text-left font-normal">scheduler</th>
                    <th className="text-right font-normal">avg reward</th>
                    <th className="text-right font-normal">interception</th>
                    <th className="text-right font-normal">hi-pri det.</th>
                  </tr>
                </thead>
                <tbody>
                  {b.rows.map((r) => (
                    <tr
                      key={r.scheduler}
                      className={
                        "border-t border-rf-grid " +
                        (r.scheduler === b.winner ? "text-rf-accent" : "")
                      }
                    >
                      <td>{r.scheduler}</td>
                      <td className="text-right">
                        {r.average_reward.mean.toFixed(2)} ±
                        {r.average_reward.ci95.toFixed(2)}
                      </td>
                      <td className="text-right">
                        {r.interception_ratio.mean.toFixed(3)} ±
                        {r.interception_ratio.ci95.toFixed(3)}
                      </td>
                      <td className="text-right">
                        {r.high_priority_detection_rate.mean.toFixed(3)} ±
                        {r.high_priority_detection_rate.ci95.toFixed(3)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {b.adaptive_minus_baseline && (
                <p className="mt-1 text-[10px] text-rf-dim">
                  adaptive − baseline: avg reward{" "}
                  <span className="text-rf-text">
                    {b.adaptive_minus_baseline.average_reward >= 0 ? "+" : ""}
                    {b.adaptive_minus_baseline.average_reward.toFixed(2)}
                  </span>
                  , interception{" "}
                  <span className="text-rf-text">
                    {b.adaptive_minus_baseline.interception_ratio >= 0 ? "+" : ""}
                    {b.adaptive_minus_baseline.interception_ratio.toFixed(3)}
                  </span>
                  , hi-pri detection{" "}
                  <span className="text-rf-text">
                    {b.adaptive_minus_baseline.high_priority_detection_rate >= 0 ? "+" : ""}
                    {b.adaptive_minus_baseline.high_priority_detection_rate.toFixed(3)}
                  </span>
                </p>
              )}
            </div>
          )}

          <div className="grid gap-2 md:grid-cols-2">
            <MetricList title="Simulation metrics (ground truth)" rows={report.metrics.simulation} />
            <MetricList title="Live metrics (proxy)" rows={report.metrics.live} />
          </div>
        </div>
      )}
    </Panel>
  );
}

function MetricList({
  title,
  rows,
}: {
  title: string;
  rows: Array<{ name: string; value: number | string; definition: string }>;
}) {
  return (
    <div className="rounded border border-rf-grid p-1.5">
      <div className="mb-1 text-[10px] uppercase tracking-wider text-rf-dim">{title}</div>
      {rows.length === 0 ? (
        <p className="text-[10px] text-rf-dim">not recorded for this session</p>
      ) : (
        <table className="w-full text-[11px] tabular-nums">
          <tbody>
            {rows.map((r) => (
              <tr key={r.name} className="border-t border-rf-grid first:border-0">
                <td className="py-0.5 pr-2 text-rf-dim" title={r.definition}>
                  {r.name}
                </td>
                <td className="py-0.5 text-right text-rf-text">
                  {typeof r.value === "number" ? r.value.toFixed(3) : r.value}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function MetricDefsPanel() {
  const [split, setSplit] = useState<MetricSplit | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .metricsSplit()
      .then(setSplit)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  return (
    <Panel title="Metric definitions — simulation vs live">
      {error ? (
        <ErrorBanner message={error} />
      ) : !split ? (
        <Loading />
      ) : (
        <div className="space-y-2">
          <p className="text-[10px] text-rf-dim">{split.note}</p>
          <div className="grid gap-2 md:grid-cols-2">
            {(
              [
                ["Simulation metrics (need ground truth)", split.simulation],
                ["Live metrics (no ground truth)", split.live],
              ] as const
            ).map(([label, defs]) => (
              <div key={label} className="rounded border border-rf-grid p-1.5">
                <div className="mb-1 text-[10px] uppercase tracking-wider text-rf-dim">
                  {label}
                </div>
                <dl className="space-y-1">
                  {defs.map((d) => (
                    <div key={d.name}>
                      <dt className="text-[11px] text-rf-scan">{d.name}</dt>
                      <dd className="text-[10px] leading-snug text-rf-dim">
                        {d.definition}
                      </dd>
                    </div>
                  ))}
                </dl>
              </div>
            ))}
          </div>
        </div>
      )}
    </Panel>
  );
}
