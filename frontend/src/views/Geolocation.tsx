import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type DFHealth, type GeoFix } from "../api";
import { useAuth } from "../auth";
import { Badge, Btn, Empty, ErrorBanner, Loading, Panel } from "../ui";

const MAP_PX = 520;
const HALF_KM = 70; // map spans -HALF_KM .. +HALF_KM on both axes

function project(x: number, y: number): [number, number] {
  const sx = ((x + HALF_KM) / (2 * HALF_KM)) * MAP_PX;
  const sy = ((HALF_KM - y) / (2 * HALF_KM)) * MAP_PX; // y up
  return [sx, sy];
}
const kmToPx = (km: number) => (km / (2 * HALF_KM)) * MAP_PX;

const SYNC_COLOR = (q: number) =>
  q >= 0.85 ? "#33d17a" : q >= 0.6 ? "#f0b429" : "#ef476f";

export default function Geolocation() {
  const { hasRole, session } = useAuth();
  const canEdit = hasRole("operator") && !session?.demo;

  const [health, setHealth] = useState<DFHealth | null>(null);
  const [fixes, setFixes] = useState<GeoFix[]>([]);
  const [summary, setSummary] = useState<{ mean_cep_km: number | null } | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [history, setHistory] = useState<Array<{ time_slot: number; x_km: number; y_km: number }>>([]);
  const [scrub, setScrub] = useState(1);
  const [err, setErr] = useState<string | null>(null);

  const refresh = useCallback(() => {
    api.dfHealth().then(setHealth).catch((e) => setErr(String(e)));
    api.dfFixes()
      .then((r) => {
        setFixes(r.fixes);
        setSummary(r.summary);
      })
      .catch((e) => setErr(String(e)));
  }, []);

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, 3000);
    return () => window.clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    if (!sel) {
      setHistory([]);
      return;
    }
    api.dfFix(sel).then((r) => {
      setHistory(r.history ?? []);
      setScrub(1);
    }).catch(() => setHistory([]));
  }, [sel, fixes.length]);

  const selectedFix = useMemo(() => fixes.find((f) => f.track_id === sel) ?? null, [fixes, sel]);
  const trail = history.slice(0, Math.max(1, Math.round(scrub * history.length)));

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 gap-2 overflow-auto p-2 lg:grid-cols-[560px_1fr]">
      <Panel
        title="Geolocation map — local plane (km, offline)"
        right={<Btn onClick={refresh}>refresh</Btn>}
      >
        {err && <ErrorBanner message={err} onRetry={refresh} />}
        <svg
          viewBox={`0 0 ${MAP_PX} ${MAP_PX}`}
          className="w-full rounded border border-rf-border bg-rf-panel2"
        >
          {/* grid */}
          {Array.from({ length: 15 }, (_, i) => {
            const p = (i / 14) * MAP_PX;
            return (
              <g key={i} stroke="#16202e" strokeWidth={1}>
                <line x1={p} y1={0} x2={p} y2={MAP_PX} />
                <line x1={0} y1={p} x2={MAP_PX} y2={p} />
              </g>
            );
          })}
          <line x1={MAP_PX / 2} y1={0} x2={MAP_PX / 2} y2={MAP_PX} stroke="#1e2a3a" />
          <line x1={0} y1={MAP_PX / 2} x2={MAP_PX} y2={MAP_PX / 2} stroke="#1e2a3a" />
          <text x={MAP_PX - 30} y={MAP_PX / 2 - 4} fill="#6b7a8f" fontSize={9}>
            +x
          </text>
          <text x={MAP_PX / 2 + 4} y={12} fill="#6b7a8f" fontSize={9}>
            +y
          </text>

          {/* nodes */}
          {health?.nodes.map((n) => {
            const [x, y] = project(n.x_km, n.y_km);
            return (
              <g key={n.node_id}>
                <rect
                  x={x - 4}
                  y={y - 4}
                  width={8}
                  height={8}
                  fill={SYNC_COLOR(n.sync_quality)}
                  stroke="#0a0e14"
                />
                <text x={x + 7} y={y + 3} fill="#6b7a8f" fontSize={9}>
                  {n.name}
                </text>
              </g>
            );
          })}

          {/* fixes */}
          {fixes.map((f) => {
            const [ex, ey] = project(f.est_x_km, f.est_y_km);
            const active = f.track_id === sel;
            return (
              <g
                key={f.track_id}
                onClick={() => setSel(f.track_id)}
                className="cursor-pointer"
              >
                {f.true_x_km != null && f.true_y_km != null && (
                  <circle
                    cx={project(f.true_x_km, f.true_y_km)[0]}
                    cy={project(f.true_x_km, f.true_y_km)[1]}
                    r={3}
                    fill="none"
                    stroke="#6b7a8f"
                    strokeDasharray="2 2"
                  />
                )}
                {Number.isFinite(f.ellipse_a_km) && (
                  <ellipse
                    cx={ex}
                    cy={ey}
                    rx={Math.min(kmToPx(f.ellipse_a_km), MAP_PX)}
                    ry={Math.min(kmToPx(f.ellipse_b_km), MAP_PX)}
                    transform={`rotate(${-f.ellipse_theta_deg} ${ex} ${ey})`}
                    fill={active ? "#3b82f622" : "#3b82f611"}
                    stroke={active ? "#33d17a" : "#3b82f6"}
                    strokeWidth={active ? 1.5 : 1}
                  />
                )}
                <circle cx={ex} cy={ey} r={active ? 4 : 3} fill={active ? "#33d17a" : "#3b82f6"} />
              </g>
            );
          })}

          {/* selected track fix-history trail */}
          {trail.length > 1 && (
            <polyline
              points={trail
                .map((h) => project(h.x_km, h.y_km).join(","))
                .join(" ")}
              fill="none"
              stroke="#33d17a"
              strokeWidth={1.5}
              opacity={0.7}
            />
          )}
        </svg>

        <div className="mt-2 flex items-center gap-3 text-[10px] text-rf-dim">
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 bg-rf-scan" /> estimate + ellipse
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-full border border-rf-dim" /> true
            (sim)
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 bg-rf-accent" /> node (sync ok)
          </span>
        </div>

        {selectedFix && history.length > 1 && (
          <label className="mt-2 flex items-center gap-2 text-[10px] text-rf-dim">
            fix history
            <input
              type="range"
              min={0.05}
              max={1}
              step={0.05}
              value={scrub}
              onChange={(e) => setScrub(Number(e.target.value))}
              className="flex-1"
            />
            <span>
              t≈{trail[trail.length - 1]?.time_slot ?? "—"}
            </span>
          </label>
        )}
      </Panel>

      <div className="flex min-h-0 flex-col gap-2 overflow-auto">
        <Panel title="Fixes">
          <div className="mb-1 text-[11px] text-rf-dim">
            {summary?.mean_cep_km != null
              ? `mean CEP ≈ ${summary.mean_cep_km} km`
              : "—"}
            {health?.rmse_km != null ? ` · RMSE ${health.rmse_km} km` : ""}
          </div>
          {fixes.length === 0 ? (
            <Empty>no fixes — run the simulation with ≥3 nodes</Empty>
          ) : (
            <table className="w-full text-[11px] tabular-nums">
              <thead className="text-rf-dim">
                <tr>
                  {["track", "est (x,y)", "CEP", "ellipse a·b", "error", "method"].map((h) => (
                    <th
                      key={h}
                      className={"font-normal " + (h === "track" ? "text-left" : "text-right")}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {fixes.map((f) => (
                  <tr
                    key={f.track_id}
                    onClick={() => setSel(f.track_id)}
                    className={
                      "cursor-pointer border-t border-rf-grid hover:bg-rf-panel2 " +
                      (f.track_id === sel ? "bg-rf-accent/10 text-rf-accent" : "")
                    }
                  >
                    <td className="text-left">{f.track_id}</td>
                    <td className="text-right">
                      {f.est_x_km.toFixed(1)}, {f.est_y_km.toFixed(1)}
                    </td>
                    <td className="text-right">{f.cep_km.toFixed(2)}</td>
                    <td className="text-right">
                      {f.ellipse_a_km.toFixed(1)}·{f.ellipse_b_km.toFixed(1)}
                    </td>
                    <td className="text-right">
                      {f.error_km != null ? f.error_km.toFixed(2) : "—"}
                    </td>
                    <td className="text-right">{f.method}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>

        <Panel title="Nodes & clock sync">
          {canEdit && <NodeEditor onSaved={refresh} health={health} />}
          {!health ? (
            <Loading />
          ) : (
            <table className="w-full text-[11px] tabular-nums">
              <thead className="text-rf-dim">
                <tr>
                  {["node", "pos (x,y)", "source", "quality", "σ ns", "kind"].map((h) => (
                    <th
                      key={h}
                      className={"font-normal " + (h === "node" ? "text-left" : "text-right")}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {health.nodes.map((n) => (
                  <tr key={n.node_id} className="border-t border-rf-grid">
                    <td className="text-left">
                      <span
                        className="mr-1 inline-block h-2 w-2"
                        style={{ background: SYNC_COLOR(n.sync_quality) }}
                      />
                      {n.name}
                    </td>
                    <td className="text-right">
                      {n.x_km.toFixed(0)}, {n.y_km.toFixed(0)}
                    </td>
                    <td className="text-right">{n.sync_source}</td>
                    <td className="text-right">{n.sync_quality.toFixed(2)}</td>
                    <td className="text-right">{n.timing_sigma_ns.toFixed(0)}</td>
                    <td className="text-right">
                      <Badge tone={n.kind === "lan" ? "good" : "dim"}>{n.kind}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
      </div>
    </div>
  );
}

function NodeEditor({
  onSaved,
  health,
}: {
  onSaved: () => void;
  health: DFHealth | null;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [err, setErr] = useState<string | null>(null);

  function start() {
    setText(
      JSON.stringify(
        (health?.nodes ?? []).map((n) => ({
          node_id: n.node_id,
          name: n.name,
          x_km: n.x_km,
          y_km: n.y_km,
          sync_source: n.sync_source,
          sync_quality: n.sync_quality,
          timing_error_ns: n.timing_sigma_ns,
        })),
        null,
        1,
      ),
    );
    setOpen(true);
  }

  async function save() {
    setErr(null);
    try {
      await api.setDfNodes(JSON.parse(text));
      setOpen(false);
      onSaved();
    } catch (e) {
      setErr(String(e));
    }
  }

  if (!open)
    return (
      <div className="mb-2">
        <Btn onClick={start}>edit node layout (JSON)</Btn>
      </div>
    );
  return (
    <div className="mb-2 flex flex-col gap-1">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={7}
        className="w-full rounded border border-rf-border bg-rf-bg p-1 font-mono text-[10px] text-rf-text"
      />
      {err && <span className="text-[10px] text-rf-alert">{err}</span>}
      <div className="flex gap-1">
        <Btn onClick={save}>save nodes</Btn>
        <Btn onClick={() => setOpen(false)}>cancel</Btn>
      </div>
    </div>
  );
}
