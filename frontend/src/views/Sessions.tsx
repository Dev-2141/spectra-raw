import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type SessionRow } from "../api";
import { useAuth } from "../auth";
import { Badge, Btn, Empty, ErrorBanner, Loading, Panel } from "../ui";

const METRIC_KEYS = [
  "average_reward",
  "probability_of_detection",
  "false_alarm_rate",
  "interception_ratio",
  "high_priority_detection_rate",
  "missed_opportunity_count",
  "scan_coverage",
] as const;

export default function Sessions() {
  const { hasRole, session: authSession } = useAuth();
  const canRecord = hasRole("operator") && !authSession?.demo;

  const [sessions, setSessions] = useState<SessionRow[] | null>(null);
  const [recording, setRecording] = useState(false);
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [cmp, setCmp] = useState<[string | null, string | null]>([null, null]);
  const [rows, setRows] = useState<Record<string, Record<string, unknown> | null>>({});
  const [q, setQ] = useState("");

  const refresh = useCallback(() => {
    api.sessions().then((r) => setSessions(r.sessions)).catch((e) => setErr(String(e)));
  }, []);
  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, 4000);
    return () => window.clearInterval(id);
  }, [refresh]);

  const filtered = useMemo(
    () =>
      (sessions ?? []).filter(
        (s) =>
          !q ||
          s.name.toLowerCase().includes(q.toLowerCase()) ||
          s.mode.includes(q) ||
          s.tags.some((t) => t.includes(q)),
      ),
    [sessions, q],
  );

  async function act(fn: () => Promise<unknown>) {
    setErr(null);
    try {
      await fn();
      refresh();
    } catch (e) {
      setErr(String(e));
    }
  }

  async function loadLastMetric(id: string) {
    if (rows[id] !== undefined) return;
    try {
      const r = await api.sessionData(id, "metrics");
      setRows((m) => ({ ...m, [id]: r.rows[r.rows.length - 1] ?? null }));
    } catch {
      setRows((m) => ({ ...m, [id]: null }));
    }
  }

  function toggleCmp(id: string) {
    setCmp(([a, b]) => {
      if (a === id) return [b, null];
      if (b === id) return [a, null];
      if (!a) return [id, b];
      if (!b) return [a, id];
      return [b, id];
    });
    loadLastMetric(id);
  }

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 gap-2 overflow-auto p-2 lg:grid-cols-[1fr_1fr]">
      <Panel
        title="Sessions"
        right={
          <span className="flex items-center gap-1.5">
            {canRecord &&
              (recording ? (
                <Btn
                  onClick={() =>
                    act(async () => {
                      await api.sessionFinish();
                      setRecording(false);
                    })
                  }
                >
                  ■ finish recording
                </Btn>
              ) : (
                <>
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="session name"
                    className="w-28 rounded border border-rf-border bg-rf-bg px-1.5 py-0.5 text-[11px] text-rf-text"
                  />
                  <Btn
                    onClick={() =>
                      act(async () => {
                        await api.sessionStart(name || "session", []);
                        setRecording(true);
                      })
                    }
                  >
                    ● start recording
                  </Btn>
                </>
              ))}
            <Btn onClick={refresh}>refresh</Btn>
          </span>
        }
      >
        {err && <ErrorBanner message={err} onRetry={refresh} />}
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="filter by name / mode / tag"
          className="mb-2 w-full rounded border border-rf-border bg-rf-bg px-1.5 py-1 text-[11px] text-rf-text"
        />
        {recording && (
          <div className="mb-2 rounded border border-rf-warn/40 bg-rf-warn/10 px-2 py-1 text-[10px] text-rf-warn">
            recording — decisions & metrics are being captured; finish to persist
          </div>
        )}
        {!sessions ? (
          <Loading />
        ) : filtered.length === 0 ? (
          <Empty>no sessions</Empty>
        ) : (
          <table className="w-full text-[11px] tabular-nums">
            <thead className="text-rf-dim">
              <tr>
                {["name", "mode", "rows", "started", "cmp"].map((h) => (
                  <th
                    key={h}
                    className={"font-normal " + (h === "name" ? "text-left" : "text-right")}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((s) => {
                const total = Object.values(s.row_counts ?? {}).reduce((a, b) => a + b, 0);
                return (
                  <tr key={s.session_id} className="border-t border-rf-grid">
                    <td className="text-left">
                      {s.name}
                      {s.status === "imported" && (
                        <Badge tone="dim">imported</Badge>
                      )}
                      {s.scenario && (
                        <span className="ml-1 text-[9px] text-rf-dim">{s.scenario}</span>
                      )}
                    </td>
                    <td className="text-right">{s.mode}</td>
                    <td className="text-right">{total}</td>
                    <td className="text-right text-rf-dim">
                      {s.started_at?.slice(5, 16)}
                    </td>
                    <td className="text-right">
                      <span className="inline-flex gap-1">
                        <button
                          onClick={() => toggleCmp(s.session_id)}
                          className={
                            "rounded border px-1 text-[10px] " +
                            (cmp.includes(s.session_id)
                              ? "border-rf-accent text-rf-accent"
                              : "border-rf-border text-rf-dim")
                          }
                        >
                          {cmp[0] === s.session_id ? "A" : cmp[1] === s.session_id ? "B" : "±"}
                        </button>
                        <a
                          href={api.sessionExportUrl(s.session_id)}
                          className="text-rf-scan hover:text-rf-accent"
                        >
                          ↓zip
                        </a>
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Panel>

      <Panel title="Compare — last metric snapshot (A vs B)">
        {!cmp[0] || !cmp[1] ? (
          <Empty>mark two sessions A and B</Empty>
        ) : (
          <table className="w-full text-[11px] tabular-nums">
            <thead className="text-rf-dim">
              <tr>
                <th className="text-left font-normal">metric</th>
                <th className="text-right font-normal">A</th>
                <th className="text-right font-normal">B</th>
                <th className="text-right font-normal">Δ</th>
              </tr>
            </thead>
            <tbody>
              {METRIC_KEYS.map((k) => {
                const a = Number(rows[cmp[0]!]?.[k] ?? NaN);
                const b = Number(rows[cmp[1]!]?.[k] ?? NaN);
                const d = b - a;
                return (
                  <tr key={k} className="border-t border-rf-grid">
                    <td className="text-left">{k}</td>
                    <td className="text-right">{Number.isFinite(a) ? a.toFixed(3) : "—"}</td>
                    <td className="text-right">{Number.isFinite(b) ? b.toFixed(3) : "—"}</td>
                    <td
                      className={
                        "text-right " +
                        (!Number.isFinite(d) ? "" : d >= 0 ? "text-rf-accent" : "text-rf-alert")
                      }
                    >
                      {Number.isFinite(d) ? (d >= 0 ? "+" : "") + d.toFixed(3) : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
