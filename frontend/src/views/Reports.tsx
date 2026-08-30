import { useCallback, useEffect, useState } from "react";
import { api, type ComparisonReport, type RunReport } from "../api";
import { Badge, Empty, Panel, Stat } from "../ui";

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
          <Empty>{error ?? "loading…"}</Empty>
        ) : (
          <div className="space-y-2">
            <div className="flex flex-wrap gap-1.5 text-[10px] text-rf-dim">
              <Badge>{run.generated_at}</Badge>
              <Badge tone="scan">{run.scheduler}</Badge>
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
    </div>
  );
}
