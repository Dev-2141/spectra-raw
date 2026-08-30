import { useCallback, useEffect, useState } from "react";
import { api, type ExplainRow } from "../api";
import { Badge, Btn, Empty, OutcomeTag, Panel } from "../ui";

export default function ExplainabilityLog() {
  const [rows, setRows] = useState<ExplainRow[]>([]);
  const [auto, setAuto] = useState(true);
  const [filter, setFilter] = useState<string>("all");
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setRows((await api.explainabilityLog(400)).log);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (!auto) return;
    const id = window.setInterval(refresh, 1500);
    return () => window.clearInterval(id);
  }, [auto, refresh]);

  const shown = rows
    .filter((r) => filter === "all" || r.outcome === filter)
    .slice()
    .reverse();

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 p-2">
      <Panel title="Explainability log — every scheduler decision and why">
        <div className="flex flex-wrap items-center gap-1.5">
          <Btn active={auto} onClick={() => setAuto((v) => !v)}>
            {auto ? "live ●" : "paused"}
          </Btn>
          <Btn onClick={refresh}>refresh</Btn>
          <span className="ml-2 text-[11px] text-rf-dim">filter</span>
          {["all", "hit", "miss", "false_alarm", "empty"].map((f) => (
            <Btn key={f} active={filter === f} onClick={() => setFilter(f)}>
              {f}
            </Btn>
          ))}
          <span className="ml-auto text-[10px] text-rf-dim">{shown.length} rows</span>
        </div>
        {error && <p className="mt-1 text-[10px] text-rf-alert">{error}</p>}
      </Panel>

      <Panel title="Decisions (newest first)" className="min-h-0 flex-1">
        {shown.length === 0 ? (
          <Empty>no decisions logged — run the simulation</Empty>
        ) : (
          <table className="w-full text-[11px]">
            <thead className="sticky top-0 bg-rf-panel text-rf-dim">
              <tr>
                <th className="text-left font-normal">t</th>
                <th className="text-left font-normal">scheduler</th>
                <th className="text-right font-normal">band</th>
                <th className="text-right font-normal">conf</th>
                <th className="px-2 text-left font-normal">pred</th>
                <th className="text-left font-normal">outcome</th>
                <th className="px-2 text-right font-normal">reward</th>
                <th className="pl-3 text-left font-normal">explanation / top factors</th>
              </tr>
            </thead>
            <tbody className="align-top tabular-nums">
              {shown.map((r, i) => (
                <tr key={`${r.time_slot}-${i}`} className="border-t border-rf-grid">
                  <td>{r.time_slot}</td>
                  <td>{r.scheduler}</td>
                  <td className="text-right text-rf-scan">{r.selected_band}</td>
                  <td className="text-right">{(r.confidence * 100).toFixed(0)}%</td>
                  <td className="px-2">{r.predicted_active === null ? "—" : r.predicted_active ? "act" : "idle"}</td>
                  <td>
                    <OutcomeTag outcome={r.outcome} />
                  </td>
                  <td className={`px-2 text-right ${r.reward >= 0 ? "text-rf-accent" : "text-rf-alert"}`}>
                    {r.reward.toFixed(1)}
                  </td>
                  <td className="max-w-[520px] whitespace-normal pl-3">
                    <div className="text-rf-text">{r.explanation}</div>
                    <div className="mt-0.5 flex flex-wrap gap-1">
                      {r.reasons.map((x, j) => (
                        <Badge key={j}>{x}</Badge>
                      ))}
                      {r.alternatives.length > 0 && (
                        <span className="text-[10px] text-rf-dim">alt: {r.alternatives.join(", ")}</span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
