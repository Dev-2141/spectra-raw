import { useCallback, useEffect, useState } from "react";
import { api, type ExplainRow, type PolicyGrid } from "../api";
import { Badge, Btn, Empty, ErrorBanner, OutcomeTag, Panel } from "../ui";

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

  const [grid, setGrid] = useState<PolicyGrid | null>(null);
  useEffect(() => {
    if (!auto) return;
    const tick = () => api.explainPolicy().then(setGrid).catch(() => undefined);
    tick();
    const id = window.setInterval(tick, 2000);
    return () => window.clearInterval(id);
  }, [auto]);

  const shown = rows
    .filter((r) => filter === "all" || r.outcome === filter)
    .slice()
    .reverse();

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 p-2">
      {grid?.available && grid.grid && grid.features && (
        <Panel title={`Policy attribution — ${grid.scheduler} (feature × band)`}>
          <div className="overflow-x-auto">
            <table className="text-[9px] tabular-nums">
              <tbody>
                {grid.features.map((f, fi) => {
                  const row = grid.grid![fi];
                  const max = Math.max(1e-6, ...row.map((v) => Math.abs(v)));
                  return (
                    <tr key={f}>
                      <td className="pr-2 text-right text-rf-dim">{f}</td>
                      {row.map((v, bi) => {
                        const a = Math.min(1, Math.abs(v) / max);
                        const col =
                          v >= 0
                            ? `rgba(51,209,122,${a.toFixed(2)})`
                            : `rgba(239,71,111,${a.toFixed(2)})`;
                        return (
                          <td
                            key={bi}
                            title={`band ${bi}: ${v}`}
                            style={{ background: col }}
                            className="h-3 w-2 border border-rf-bg"
                          />
                        );
                      })}
                    </tr>
                  );
                })}
                {grid.q_values && (
                  <tr>
                    <td className="pr-2 text-right text-rf-scan">Q</td>
                    {grid.q_values.map((q, bi) => (
                      <td key={bi} className="px-0.5 text-rf-scan" title={`band ${bi}`}>
                        {q.toFixed(1)}
                      </td>
                    ))}
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
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
        {error && (
          <div className="mt-1">
            <ErrorBanner message={error} onRetry={refresh} />
          </div>
        )}
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
                <th className="px-2 text-left font-normal">counterfactual</th>
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
                  <td className="px-2 text-[10px] text-rf-dim">
                    {r.counterfactual
                      ? `→b${r.counterfactual.alt_band} if ${r.counterfactual.flip_factor} (Δ${r.counterfactual.margin})`
                      : "—"}
                  </td>
                  <td className="max-w-[480px] whitespace-normal pl-3">
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
