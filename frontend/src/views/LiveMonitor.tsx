import type { SimControls } from "../useSim";
import { LineChart, SpectrumChart, Waterfall } from "../charts";
import { Badge, Empty, ErrorBanner, Loading, OutcomeTag, Panel, Stat } from "../ui";
import type { SimState } from "../api";

export default function LiveMonitor({ sim }: { sim: SimControls }) {
  const s = sim.state;
  if (!s)
    return sim.error ? (
      <div className="p-3">
        <ErrorBanner message={sim.error} onRetry={sim.refresh} />
      </div>
    ) : (
      <Loading label="connecting to backend…" />
    );
  const m = s.metrics;
  const last = s.last_step ?? null;

  return (
    <div className="grid min-h-0 flex-1 grid-cols-[1fr_300px] grid-rows-[1fr_190px] gap-2 p-2">
      {/* center column: spectrum + waterfall */}
      <div className="flex min-h-0 flex-col gap-2">
        <Panel
          title="Spectrum — power vs band"
          right={
            <span className="flex gap-1.5 text-[10px] text-rf-dim">
              <Badge tone="scan">scanning b{s.receiver.current_band}</Badge>
              <Badge tone="good">active</Badge>
              <Badge tone="warn">threshold</Badge>
              <span>t={s.time_slot}</span>
              <span>{s.scheduler}</span>
            </span>
          }
          className="h-[42%]"
        >
          <div className="h-full">
            <SpectrumChart
              power={s.spectrum.power_db}
              active={s.spectrum.active}
              threshold={s.spectrum.threshold_db}
              currentBand={s.receiver.current_band}
              height={150}
            />
          </div>
        </Panel>
        <Panel
          title="Waterfall — band × recent time  (scan path overlaid)"
          right={
            <span className="flex gap-1.5 text-[10px] text-rf-dim">
              <Badge tone="good">hit</Badge>
              <Badge tone="warn">miss</Badge>
              <Badge tone="bad">false alarm</Badge>
              <Badge tone="scan">empty</Badge>
            </span>
          }
          className="min-h-0 flex-1"
        >
          <Waterfall
            power={s.waterfall.power_db}
            startSlot={s.waterfall.start_slot}
            scanPath={s.scan_path}
            height={260}
          />
        </Panel>
      </div>

      {/* right column: metrics + decision */}
      <div className="flex min-h-0 flex-col gap-2 overflow-y-auto">
        <Panel title="Metrics (live)">
          <div className="grid grid-cols-2 gap-1.5">
            <Stat label="P(detection)" value={m.probability_of_detection.toFixed(3)} tone="good" />
            <Stat label="false alarm rate" value={m.false_alarm_rate.toFixed(3)} tone={m.false_alarm_rate > 0.05 ? "bad" : undefined} />
            <Stat label="interception" value={m.interception_ratio.toFixed(3)} hint={`${m.emitter_events_detected}/${m.emitter_events_total} events`} />
            <Stat label="avg intercept delay" value={`${m.average_intercept_delay.toFixed(1)}`} hint="slots" />
            <Stat label="avg reward" value={m.average_reward.toFixed(2)} tone={m.average_reward >= 0 ? "good" : "bad"} />
            <Stat label="hi-priority det." value={m.high_priority_detection_rate.toFixed(3)} tone="warn" />
            <Stat label="coverage" value={m.scan_coverage.toFixed(3)} />
            <Stat label="missed opps" value={m.missed_opportunity_count} tone="bad" />
            <Stat label="revisit time" value={m.average_revisit_time.toFixed(1)} hint="slots" />
            <Stat label="selected band" value={s.receiver.current_band} tone="scan" />
          </div>
        </Panel>

        <Panel title="Active decision">
          {last ? <DecisionCard step={last} /> : <Empty>step to see the scheduler reason</Empty>}
        </Panel>
      </div>

      {/* bottom: event log + reward timeline */}
      <Panel title="Event log">
        <EventLog scanPath={s.scan_path} />
      </Panel>
      <Panel title="Reward timeline">
        {s.reward_series.length > 1 ? (
          <LineChart
            series={[
              {
                name: "reward",
                color: "#33d17a",
                points: s.reward_series.map((r) => r.reward),
              },
            ]}
            height={150}
            zeroBaseline
          />
        ) : (
          <Empty>no rewards yet</Empty>
        )}
      </Panel>
    </div>
  );
}

function DecisionCard({ step }: { step: NonNullable<SimState["last_step"]> }) {
  const d = step.decision;
  const det = step.detection;
  const outcome = det.detected && det.true_active ? "hit" : det.false_alarm ? "false_alarm" : det.true_active ? "miss" : "empty";
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-[11px]">
        <span className="text-rf-dim">t={step.time_slot}</span>
        <span className="flex items-center gap-1.5">
          band <span className="text-rf-scan">{d.selected_band}</span>
          <OutcomeTag outcome={outcome} />
        </span>
      </div>
      <div className="grid grid-cols-3 gap-1 text-[10px]">
        <div className="rounded border border-rf-border bg-rf-panel2 p-1">
          <div className="text-rf-dim">confidence</div>
          <div className="text-rf-text">{(d.confidence * 100).toFixed(0)}%</div>
        </div>
        <div className="rounded border border-rf-border bg-rf-panel2 p-1">
          <div className="text-rf-dim">pred. active</div>
          <div className="text-rf-text">{d.predicted_active === null ? "—" : d.predicted_active ? "yes" : "no"}</div>
        </div>
        <div className="rounded border border-rf-border bg-rf-panel2 p-1">
          <div className="text-rf-dim">reward</div>
          <div className={step.reward >= 0 ? "text-rf-accent" : "text-rf-alert"}>{step.reward.toFixed(1)}</div>
        </div>
      </div>
      <p className="text-[11px] leading-relaxed text-rf-text">{d.explanation}</p>
      <ul className="space-y-0.5 text-[10px] text-rf-dim">
        {d.reasons.map((r, i) => (
          <li key={i}>› {r}</li>
        ))}
      </ul>
      {d.alternatives.length > 0 && (
        <div className="text-[10px] text-rf-dim">alternatives: {d.alternatives.join(", ")}</div>
      )}
      <div className="text-[10px] text-rf-dim">
        {Object.entries(step.reward_breakdown).map(([k, v]) => `${k} ${v}`).join(" · ") || "—"}
      </div>
    </div>
  );
}

function EventLog({ scanPath }: { scanPath: SimState["scan_path"] }) {
  if (scanPath.length === 0) return <Empty>no events</Empty>;
  const rows = scanPath.slice(-40).reverse();
  return (
    <table className="w-full text-[11px]">
      <thead className="sticky top-0 bg-rf-panel text-rf-dim">
        <tr>
          <th className="text-left font-normal">t</th>
          <th className="text-left font-normal">band</th>
          <th className="text-left font-normal">outcome</th>
          <th className="text-right font-normal">reward</th>
        </tr>
      </thead>
      <tbody className="tabular-nums">
        {rows.map((r, i) => {
          const outcome = r.detected ? "hit" : r.false_alarm ? "false_alarm" : r.true_active ? "miss" : "empty";
          return (
            <tr key={i} className="border-t border-rf-grid">
              <td>{r.time_slot}</td>
              <td>{r.scanned_band}</td>
              <td>
                <OutcomeTag outcome={outcome} />
              </td>
              <td className={`text-right ${r.reward >= 0 ? "text-rf-accent" : "text-rf-alert"}`}>
                {r.reward.toFixed(1)}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
