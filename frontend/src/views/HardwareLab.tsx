import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  type HardwareConfig,
  type HardwareDeviceInfo,
  type HardwareStatus,
  type RecordingMeta,
  type SourceMode,
} from "../api";
import { useAuth } from "../auth";
import { Badge, Btn, Empty, ErrorBanner, Panel } from "../ui";

const SOURCES: SourceMode[] = [
  "file_replay",
  "rtl_power",
  "hackrf_sweep",
  "soapysdr",
];

const DEFAULT_CFG: HardwareConfig = {
  source_mode: "file_replay",
  start_freq_hz: 88_000_000,
  stop_freq_hz: 108_000_000,
  bin_hz: 100_000,
  sweep_interval_ms: 250,
  gain_db: null,
  num_bands: 64,
  recording_id: null,
  replay_speed: 4,
  replay_loop: true,
};

export default function HardwareLab() {
  const { hasRole, session } = useAuth();
  const canControl = hasRole("operator") && !session?.demo;

  const [cfg, setCfg] = useState<HardwareConfig>(DEFAULT_CFG);
  const [status, setStatus] = useState<HardwareStatus | null>(null);
  const [devices, setDevices] = useState<HardwareDeviceInfo[]>([]);
  const [recordings, setRecordings] = useState<RecordingMeta[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    api.hwStatus().then(setStatus).catch((e) => setErr(String(e)));
    api.hwDevices().then((r) => setDevices(r.devices)).catch(() => undefined);
    api.hwRecordings().then((r) => setRecordings(r.recordings)).catch(() => undefined);
  }, []);

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, 2000);
    return () => window.clearInterval(id);
  }, [refresh]);

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

  const running = !!status?.running;
  const set = <K extends keyof HardwareConfig>(k: K, v: HardwareConfig[K]) =>
    setCfg((c) => ({ ...c, [k]: v }));

  const replayRecs = useMemo(
    () => recordings.filter((r) => r.frame_count > 0),
    [recordings],
  );

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 gap-2 overflow-auto p-2 lg:grid-cols-3">
      {/* source + config */}
      <Panel title="Source & sweep config" className="lg:col-span-1">
        {!canControl && (
          <div className="mb-2 rounded border border-rf-border bg-rf-panel2 px-2 py-1 text-[10px] text-rf-dim">
            read-only — hardware control needs the operator role
          </div>
        )}
        {err && <ErrorBanner message={err} onRetry={() => setErr(null)} />}

        <label className="mb-2 flex items-center gap-2 text-[11px] text-rf-dim">
          <span className="w-24">source</span>
          <select
            disabled={!canControl || running}
            value={cfg.source_mode}
            onChange={(e) => set("source_mode", e.target.value as SourceMode)}
            className="flex-1 rounded border border-rf-border bg-rf-bg px-1.5 py-1 text-[12px] text-rf-text"
          >
            {SOURCES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>

        {cfg.source_mode === "file_replay" && (
          <label className="mb-2 flex items-center gap-2 text-[11px] text-rf-dim">
            <span className="w-24">recording</span>
            <select
              disabled={!canControl || running}
              value={cfg.recording_id ?? ""}
              onChange={(e) => set("recording_id", e.target.value || null)}
              className="flex-1 rounded border border-rf-border bg-rf-bg px-1.5 py-1 text-[12px] text-rf-text"
            >
              <option value="">— pick a recording —</option>
              {replayRecs.map((r) => (
                <option key={r.recording_id} value={r.recording_id}>
                  {r.name} · {r.frame_count} frames
                </option>
              ))}
            </select>
          </label>
        )}

        {(
          [
            ["start_freq_hz", "start Hz", 1e6],
            ["stop_freq_hz", "stop Hz", 1e6],
            ["bin_hz", "bin Hz", 1e3],
            ["sweep_interval_ms", "interval ms", 10],
            ["num_bands", "band grid", 1],
            ["replay_speed", "replay ×", 1],
          ] as const
        ).map(([k, label, step]) => (
          <label
            key={k}
            className="mb-1 flex items-center justify-between gap-2 text-[11px] text-rf-dim"
          >
            <span>{label}</span>
            <input
              type="number"
              step={step}
              disabled={!canControl || running}
              value={cfg[k] as number}
              onChange={(e) => set(k, Number(e.target.value) as never)}
              className="w-28 rounded border border-rf-border bg-rf-bg px-1.5 py-0.5 text-right tabular-nums text-rf-text"
            />
          </label>
        ))}
        <label className="mb-2 flex items-center justify-between gap-2 text-[11px] text-rf-dim">
          <span>gain dB (blank = auto)</span>
          <input
            type="number"
            disabled={!canControl || running}
            value={cfg.gain_db ?? ""}
            onChange={(e) =>
              set("gain_db", e.target.value === "" ? null : Number(e.target.value))
            }
            className="w-28 rounded border border-rf-border bg-rf-bg px-1.5 py-0.5 text-right tabular-nums text-rf-text"
          />
        </label>

        <div className="mt-2 flex gap-1">
          {!running ? (
            <Btn
              disabled={!canControl || busy}
              onClick={() => act(() => api.hwStart(cfg))}
            >
              ▶ start scan
            </Btn>
          ) : (
            <Btn disabled={!canControl || busy} onClick={() => act(() => api.hwStop())}>
              ❚❚ stop scan
            </Btn>
          )}
          {running && !status?.recording && (
            <Btn
              disabled={!canControl || busy}
              onClick={() => act(() => api.hwRecordStart("session"))}
            >
              ● record
            </Btn>
          )}
          {running && status?.recording && (
            <Btn
              disabled={!canControl || busy}
              onClick={() => act(() => api.hwRecordStop())}
            >
              ■ stop rec
            </Btn>
          )}
        </div>
      </Panel>

      {/* status */}
      <Panel
        title="Status"
        className="lg:col-span-1"
        right={<Btn onClick={refresh}>refresh</Btn>}
      >
        {!status ? (
          <Empty>no status</Empty>
        ) : (
          <div className="flex flex-col gap-1 text-[12px]">
            <Row k="source" v={status.source_mode} />
            <Row
              k="state"
              v={status.running ? "running" : "stopped"}
              tone={status.running ? "good" : "dim"}
            />
            <Row k="device" v={status.device_label ?? "—"} />
            <Row k="frames read" v={String(status.frames_read)} />
            <Row k="frame rate" v={`${status.frame_rate_hz.toFixed(2)} Hz`} />
            <Row k="buffer" v={`${status.buffer_len} frames`} />
            <Row
              k="recording"
              v={status.recording ? (status.recording_id ?? "yes") : "no"}
              tone={status.recording ? "warn" : "dim"}
            />
            <Row
              k="transmit"
              v={String(status.transmit_capability)}
              tone="good"
            />
            <Row k="hardware mode" v={status.hardware_mode} tone="good" />
            {status.detail && <Row k="detail" v={status.detail} />}
            {status.error && (
              <div className="mt-1 rounded border border-rf-alert/40 bg-rf-alert/10 px-2 py-1 text-[10px] text-rf-alert">
                {status.error}
              </div>
            )}
          </div>
        )}
      </Panel>

      {/* devices + recordings */}
      <Panel title="Devices & recordings" className="lg:col-span-1">
        <div className="mb-1 text-[10px] uppercase tracking-wider text-rf-dim">
          devices
        </div>
        {devices.length === 0 ? (
          <Empty>none detected</Empty>
        ) : (
          <ul className="mb-3 flex flex-col gap-1 text-[11px]">
            {devices.map((d) => (
              <li
                key={d.id + d.driver}
                className="flex items-center justify-between rounded border border-rf-border bg-rf-panel2 px-2 py-1"
              >
                <span>
                  {d.driver}
                  <span className="ml-1 text-rf-dim">{d.note}</span>
                </span>
                <Badge tone={d.available ? "good" : "dim"}>
                  {d.available ? "ready" : "n/a"}
                </Badge>
              </li>
            ))}
          </ul>
        )}

        <div className="mb-1 text-[10px] uppercase tracking-wider text-rf-dim">
          recordings
        </div>
        {recordings.length === 0 ? (
          <Empty>no recordings yet</Empty>
        ) : (
          <ul className="flex flex-col gap-1 text-[11px]">
            {recordings.map((r) => (
              <li
                key={r.recording_id}
                className="rounded border border-rf-border bg-rf-panel2 px-2 py-1"
              >
                <div className="flex items-center justify-between">
                  <span>{r.name}</span>
                  <span className="text-rf-dim">{r.frame_count} frames</span>
                </div>
                <div className="mt-0.5 flex items-center justify-between text-[10px] text-rf-dim">
                  <span>
                    {(r.start_freq_hz / 1e6).toFixed(1)}–
                    {(r.stop_freq_hz / 1e6).toFixed(1)} MHz · {r.source}
                  </span>
                  {cfg.source_mode === "file_replay" && (
                    <button
                      disabled={!canControl || running}
                      onClick={() =>
                        setCfg((c) => ({
                          ...c,
                          source_mode: "file_replay",
                          recording_id: r.recording_id,
                        }))
                      }
                      className="underline hover:no-underline disabled:opacity-40"
                    >
                      use for replay
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}

function Row({
  k,
  v,
  tone,
}: {
  k: string;
  v: string;
  tone?: "good" | "warn" | "dim";
}) {
  const color =
    tone === "good"
      ? "text-rf-accent"
      : tone === "warn"
        ? "text-rf-warn"
        : tone === "dim"
          ? "text-rf-dim"
          : "text-rf-text";
  return (
    <div className="flex items-center justify-between">
      <span className="text-rf-dim">{k}</span>
      <span className={`tabular-nums ${color}`}>{v}</span>
    </div>
  );
}
