import { useCallback, useEffect, useState } from "react";
import {
  api,
  type CalibrationProfile,
  type RealityGapReport,
  type RecordingMeta,
} from "../api";
import { useAuth } from "../auth";
import { BarChart } from "../charts";
import { Badge, Btn, Empty, ErrorBanner, Loading, Panel } from "../ui";

export default function Sim2Real() {
  const { hasRole, session } = useAuth();
  const canRun = hasRole("operator") && !session?.demo;

  const [recordings, setRecordings] = useState<RecordingMeta[]>([]);
  const [profiles, setProfiles] = useState<CalibrationProfile[]>([]);
  const [recId, setRecId] = useState("");
  const [profId, setProfId] = useState("");
  const [scheduler, setScheduler] = useState("priority");
  const [steps, setSteps] = useState(600);
  const [shift, setShift] = useState(0);
  const [report, setReport] = useState<RealityGapReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const refresh = useCallback(() => {
    api.hwRecordings().then((r) => setRecordings(r.recordings)).catch(() => undefined);
    api.s2rProfiles().then((r) => setProfiles(r.profiles)).catch(() => undefined);
  }, []);
  useEffect(refresh, [refresh]);

  async function act(fn: () => Promise<unknown>) {
    setErr(null);
    setBusy(true);
    try {
      await fn();
      refresh();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 gap-2 overflow-auto p-2 lg:grid-cols-[340px_1fr]">
      <div className="flex min-h-0 flex-col gap-2 overflow-auto">
        <Panel title="1 · Calibrate a profile from a recording">
          {err && <ErrorBanner message={err} onRetry={() => setErr(null)} />}
          <label className="mb-2 flex flex-col gap-1 text-[11px] text-rf-dim">
            recording
            <select
              value={recId}
              onChange={(e) => setRecId(e.target.value)}
              className="rounded border border-rf-border bg-rf-bg px-1.5 py-1 text-[12px] text-rf-text"
            >
              <option value="">— pick a recording —</option>
              {recordings.map((r) => (
                <option key={r.recording_id} value={r.recording_id}>
                  {r.name} · {r.frame_count} frames
                </option>
              ))}
            </select>
          </label>
          <Btn
            disabled={!canRun || !recId || busy}
            onClick={() =>
              act(async () => {
                const p = await api.s2rCalibrate(recId);
                setProfId(p.profile_id);
              })
            }
          >
            calibrate
          </Btn>
          {recordings.length === 0 && (
            <p className="mt-1 text-[10px] text-rf-dim">
              no recordings — record one in Hardware Lab first
            </p>
          )}
        </Panel>

        <Panel title="Profiles">
          {profiles.length === 0 ? (
            <Empty>no calibration profiles</Empty>
          ) : (
            <ul className="flex flex-col gap-1 text-[11px]">
              {profiles.map((p) => (
                <li key={p.profile_id}>
                  <button
                    onClick={() => setProfId(p.profile_id)}
                    className={
                      "w-full rounded border px-2 py-1 text-left " +
                      (p.profile_id === profId
                        ? "border-rf-accent bg-rf-accent/10 text-rf-accent"
                        : "border-rf-border hover:border-rf-dim")
                    }
                  >
                    <div className="flex justify-between">
                      <span>{p.name}</span>
                      <span className="text-rf-dim">{p.num_bands} bands</span>
                    </div>
                    <div className="text-[9px] text-rf-dim">
                      noise {p.noise_floor_db} dB · density {p.emitter_density} · SNR{" "}
                      {p.snr_min_db}–{p.snr_max_db}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="2 · Measure the reality gap">
          <label className="mb-1 flex items-center justify-between text-[11px] text-rf-dim">
            scheduler
            <input
              value={scheduler}
              onChange={(e) => setScheduler(e.target.value)}
              className="w-32 rounded border border-rf-border bg-rf-bg px-1.5 py-0.5 text-rf-text"
            />
          </label>
          <label className="mb-1 flex items-center justify-between text-[11px] text-rf-dim">
            steps
            <input
              type="number"
              value={steps}
              step={100}
              onChange={(e) => setSteps(Number(e.target.value))}
              className="w-24 rounded border border-rf-border bg-rf-bg px-1.5 py-0.5 text-right tabular-nums text-rf-text"
            />
          </label>
          <label className="mb-2 flex items-center justify-between text-[11px] text-rf-dim">
            noise mismatch dB (test)
            <input
              type="number"
              value={shift}
              step={2}
              onChange={(e) => setShift(Number(e.target.value))}
              className="w-24 rounded border border-rf-border bg-rf-bg px-1.5 py-0.5 text-right tabular-nums text-rf-text"
            />
          </label>
          <Btn
            active
            disabled={!recId || !profId || busy}
            onClick={() =>
              act(async () => {
                setReport(
                  await api.s2rGap({
                    recording_id: recId,
                    profile_id: profId,
                    scheduler,
                    steps,
                    noise_shift_db: shift,
                  }),
                );
              })
            }
          >
            {busy ? "computing…" : "compute gap"}
          </Btn>
        </Panel>
      </div>

      <Panel title="Reality-gap report">
        {busy && !report ? (
          <Loading label="running recording + calibrated sim…" />
        ) : !report ? (
          <Empty>calibrate a profile, then compute the gap</Empty>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-3">
              <Badge
                tone={
                  report.gap_score < 0.15
                    ? "good"
                    : report.gap_score < 0.4
                      ? "warn"
                      : "bad"
                }
              >
                gap score {report.gap_score}
              </Badge>
              <span className="text-[11px] text-rf-dim">{report.narrative}</span>
            </div>

            <table className="w-full text-[11px] tabular-nums">
              <thead className="text-rf-dim">
                <tr>
                  {["metric", "recording", "calibrated sim", "gap"].map((h) => (
                    <th
                      key={h}
                      className={"font-normal " + (h === "metric" ? "text-left" : "text-right")}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {report.metrics.map((m) => (
                  <tr key={m.metric} className="border-t border-rf-grid">
                    <td className="text-left">{m.metric}</td>
                    <td className="text-right">{m.recording_value}</td>
                    <td className="text-right">{m.sim_value}</td>
                    <td
                      className={
                        "text-right " +
                        (m.gap > 0.4 ? "text-rf-alert" : m.gap > 0.15 ? "text-rf-warn" : "")
                      }
                    >
                      {m.gap}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            <BarChart
              data={report.metrics.map((m) => ({
                label: m.metric,
                value: m.gap,
                color: m.gap > 0.4 ? "#ef476f" : m.gap > 0.15 ? "#f0b429" : "#33d17a",
              }))}
              valueFormat={(v) => v.toFixed(2)}
            />
          </div>
        )}
      </Panel>
    </div>
  );
}
