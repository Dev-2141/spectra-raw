import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type EmitterTrack, type ForecastReport } from "../api";
import { useAuth } from "../auth";
import { Badge, Btn, Empty, ErrorBanner, Loading, Panel } from "../ui";

export default function SignalsTracks() {
  const { hasRole, session } = useAuth();
  const canEdit = hasRole("operator") && !session?.demo;

  const [tracks, setTracks] = useState<EmitterTrack[] | null>(null);
  const [forecast, setForecast] = useState<ForecastReport | null>(null);
  const [selId, setSelId] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const refresh = useCallback(() => {
    api.tracks().then((r) => setTracks(r.tracks)).catch((e) => setErr(String(e)));
    api.forecast().then(setForecast).catch(() => undefined);
  }, []);

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, 3000);
    return () => window.clearInterval(id);
  }, [refresh]);

  const selected = useMemo(
    () => tracks?.find((t) => t.track_id === selId) ?? null,
    [tracks, selId],
  );

  async function addToLibrary(tr: EmitterTrack) {
    setMsg(null);
    setErr(null);
    try {
      await api.libraryCreate({
        name: `TRK ${tr.track_id}`,
        behavior:
          tr.class === "unknown"
            ? tr.freq_behavior === "fixed"
              ? "periodic"
              : "hopping"
            : tr.class,
        modulation: tr.modulation,
        home_band: tr.primary_band,
        pri_slots: tr.pri_estimate,
        pri_jitter: tr.pri_jitter,
        hop_span_bands: tr.bands.length,
        duty_cycle: tr.duty_cycle,
        threat: tr.threat,
        notes: `captured from ${tr.track_id} @ t${tr.first_seen}`,
      });
      setMsg(`added ${tr.track_id} to the library`);
    } catch (e) {
      setErr(String(e));
    }
  }

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 gap-2 overflow-auto p-2 lg:grid-cols-[1.4fr_1fr]">
      <Panel
        title="Emitter tracks"
        right={<Btn onClick={refresh}>refresh</Btn>}
        className="min-h-0"
      >
        {err && <ErrorBanner message={err} onRetry={refresh} />}
        {msg && (
          <div className="mb-2 rounded border border-rf-accent/40 bg-rf-accent/10 px-2 py-1 text-[11px] text-rf-accent">
            {msg}
          </div>
        )}
        {!tracks ? (
          <Loading />
        ) : tracks.length === 0 ? (
          <Empty>no tracks yet — run the simulation</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[620px] text-[11px] tabular-nums">
              <thead className="text-rf-dim">
                <tr>
                  {["track", "bands", "behavior", "class", "conf", "top match", "threat", "age"].map(
                    (h) => (
                      <th
                        key={h}
                        className={"font-normal " + (h === "track" ? "text-left" : "text-right")}
                      >
                        {h}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {tracks.map((t) => (
                  <tr
                    key={t.track_id}
                    onClick={() => setSelId(t.track_id)}
                    className={
                      "cursor-pointer border-t border-rf-grid hover:bg-rf-panel2 " +
                      (t.track_id === selId ? "bg-rf-accent/10 text-rf-accent" : "")
                    }
                  >
                    <td className="text-left">
                      {t.track_id}
                      {t.is_synthetic_effect && (
                        <span className="ml-1 text-rf-warn">✦</span>
                      )}
                    </td>
                    <td className="text-right">
                      {t.bands[0]}
                      {t.bands.length > 1 ? `–${t.bands[t.bands.length - 1]}` : ""}
                    </td>
                    <td className="text-right">{t.freq_behavior}</td>
                    <td className="text-right">{t.class}</td>
                    <td className="text-right">{t.class_confidence.toFixed(2)}</td>
                    <td className="text-right">
                      {t.library_matches[0]
                        ? `${t.library_matches[0].name} ${t.library_matches[0].score.toFixed(2)}`
                        : "—"}
                    </td>
                    <td
                      className={
                        "text-right " + (t.high_priority ? "text-rf-alert" : "")
                      }
                    >
                      {t.threat.toFixed(2)}
                    </td>
                    <td className="text-right">{t.age_slots}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <div className="flex min-h-0 flex-col gap-2 overflow-auto">
        <Panel title="Track detail">
          {!selected ? (
            <Empty>select a track</Empty>
          ) : (
            <div className="flex flex-col gap-2 text-[11px]">
              <div className="flex items-center justify-between">
                <span className="text-rf-accent">{selected.track_id}</span>
                <span className="flex gap-1">
                  <Badge tone={selected.high_priority ? "bad" : "dim"}>
                    threat {selected.threat.toFixed(2)}
                  </Badge>
                  {selected.is_synthetic_effect && (
                    <Badge tone="warn">synthetic effect</Badge>
                  )}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-rf-dim">
                {(
                  [
                    ["class", `${selected.class} (${selected.class_confidence.toFixed(2)})`],
                    ["freq behavior", selected.freq_behavior],
                    ["spectral shape", selected.spectral_shape],
                    ["modulation", selected.modulation],
                    ["PRI est", `${selected.pri_estimate} (jit ${selected.pri_jitter})`],
                    ["duty cycle", selected.duty_cycle.toFixed(3)],
                    ["SNR mean", `${selected.snr_mean_db} dB`],
                    ["runs", String(selected.run_count)],
                    ["bands", selected.bands.join(", ")],
                    ["seen", `t${selected.first_seen}–${selected.last_seen}`],
                  ] as const
                ).map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-2">
                    <span>{k}</span>
                    <span className="text-rf-text">{v}</span>
                  </div>
                ))}
              </div>

              <div>
                <div className="mb-1 text-[10px] uppercase tracking-wider text-rf-dim">
                  class probabilities
                </div>
                {Object.entries(selected.class_probabilities)
                  .sort((a, b) => b[1] - a[1])
                  .map(([c, p]) => (
                    <div key={c} className="flex items-center gap-2">
                      <span className="w-16 text-rf-dim">{c}</span>
                      <div className="h-2 flex-1 rounded bg-rf-panel2">
                        <div
                          className="h-full rounded bg-rf-accent/60"
                          style={{ width: `${p * 100}%` }}
                        />
                      </div>
                      <span className="w-10 text-right tabular-nums">{p.toFixed(2)}</span>
                    </div>
                  ))}
              </div>

              <div>
                <div className="mb-1 text-[10px] uppercase tracking-wider text-rf-dim">
                  library matches
                </div>
                {selected.library_matches.length === 0 ? (
                  <span className="text-rf-dim">no match</span>
                ) : (
                  <ul className="flex flex-col gap-0.5">
                    {selected.library_matches.map((m) => (
                      <li key={m.entry_id} className="flex justify-between">
                        <span>
                          {m.name}{" "}
                          <span className="text-rf-dim">
                            ({m.behavior}, threat {m.threat})
                          </span>
                        </span>
                        <span className="tabular-nums text-rf-accent">
                          {m.score.toFixed(3)}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <Btn disabled={!canEdit} onClick={() => addToLibrary(selected)}>
                + add as library entry
              </Btn>
            </div>
          )}
        </Panel>

        <Panel title="Forecast — next periodic activations">
          {!forecast || forecast.forecast.length === 0 ? (
            <Empty>no periodic tracks detected</Empty>
          ) : (
            <table className="w-full text-[11px] tabular-nums">
              <thead className="text-rf-dim">
                <tr>
                  <th className="text-left font-normal">track</th>
                  <th className="text-right font-normal">band</th>
                  <th className="text-right font-normal">PRI</th>
                  <th className="text-right font-normal">next in</th>
                  <th className="text-right font-normal">conf</th>
                </tr>
              </thead>
              <tbody>
                {forecast.forecast.map((f) => (
                  <tr key={f.track_id} className="border-t border-rf-grid">
                    <td className="text-left">{f.track_id}</td>
                    <td className="text-right">{f.band}</td>
                    <td className="text-right">{f.pri_slots}</td>
                    <td className="text-right text-rf-accent">{f.slots_until_next}</td>
                    <td className="text-right">{f.confidence.toFixed(2)}</td>
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
