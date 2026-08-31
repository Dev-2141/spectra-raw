import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  type EWEffectSpec,
  type Scenario,
  type ScenarioSaveBody,
} from "../api";
import { useAuth } from "../auth";
import { Badge, Btn, Empty, ErrorBanner, Loading, Panel } from "../ui";

const EFFECT_KINDS: EWEffectSpec["kind"][] = [
  "barrage_noise",
  "spot_jam",
  "swept_jam",
  "repeater_ghost",
  "spoof_track",
];

function blankEffect(): EWEffectSpec {
  return {
    kind: "spot_jam",
    label: "",
    start_slot: 0,
    stop_slot: 1000,
    band_lo: 0,
    band_hi: 0,
    power_db: 20,
    sweep_rate_bands_per_slot: 0.5,
    source_band: 0,
    target_band: 0,
    delay_slots: 3,
    spoof_period_slots: 18,
    spoof_pulse_slots: 2,
    spoof_snr_db: 12,
  };
}

export default function ScenarioEditor() {
  const { hasRole, session } = useAuth();
  const canEdit = hasRole("operator") && !session?.demo;

  const [list, setList] = useState<Scenario[] | null>(null);
  const [selId, setSelId] = useState<string | null>(null);
  const [draft, setDraft] = useState<ScenarioSaveBody | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    api
      .scenarios()
      .then((r) => setList(r.scenarios))
      .catch((e) => setErr(String(e)));
  }, []);
  useEffect(refresh, [refresh]);

  const selected = useMemo(
    () => list?.find((s) => s.scenario_id === selId) ?? null,
    [list, selId],
  );
  const editingBuiltin = !!selected?.builtin;

  function pick(s: Scenario) {
    setSelId(s.scenario_id);
    setMsg(null);
    setErr(null);
    setDraft({
      name: s.builtin ? `${s.name} (copy)` : s.name,
      description: s.description,
      tags: s.tags.filter((t) => t !== "builtin"),
      environment: { ...s.environment },
      receiver: { ...s.receiver },
      effects: s.effects.map((e) => ({ ...e })),
    });
  }

  async function act(fn: () => Promise<unknown>, ok?: string) {
    setErr(null);
    setMsg(null);
    setBusy(true);
    try {
      await fn();
      if (ok) setMsg(ok);
      refresh();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  const setEnv = (k: string, v: number) =>
    setDraft((d) => (d ? { ...d, environment: { ...d.environment, [k]: v } } : d));
  const setEffect = (i: number, patch: Partial<EWEffectSpec>) =>
    setDraft((d) =>
      d
        ? { ...d, effects: d.effects.map((e, j) => (j === i ? { ...e, ...patch } : e)) }
        : d,
    );

  function exportJson() {
    if (!selected) return;
    const blob = new Blob([JSON.stringify(selected, null, 2)], {
      type: "application/json",
    });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${selected.name.replace(/\s+/g, "_")}.scenario.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function importJson(text: string) {
    try {
      const s = JSON.parse(text) as Scenario;
      setSelId(null);
      setDraft({
        name: (s.name || "imported") + " (imported)",
        description: s.description ?? "",
        tags: (s.tags ?? []).filter((t) => t !== "builtin"),
        environment: s.environment,
        receiver: s.receiver,
        effects: (s.effects ?? []).map((e) => ({ ...blankEffect(), ...e })),
      });
      setMsg("imported — review and Save");
    } catch (e) {
      setErr("invalid scenario JSON: " + String(e));
    }
  }

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 gap-2 overflow-auto p-2 lg:grid-cols-[280px_1fr]">
      <Panel title="Scenarios" right={<Btn onClick={refresh}>refresh</Btn>}>
        {err && <ErrorBanner message={err} />}
        {!list ? (
          <Loading />
        ) : (
          <ul className="flex flex-col gap-1 text-[11px]">
            {list.map((s) => (
              <li key={s.scenario_id}>
                <button
                  onClick={() => pick(s)}
                  className={
                    "w-full rounded border px-2 py-1 text-left transition " +
                    (s.scenario_id === selId
                      ? "border-rf-accent bg-rf-accent/10 text-rf-accent"
                      : "border-rf-border bg-rf-panel2 hover:border-rf-accent")
                  }
                >
                  <div className="flex items-center justify-between">
                    <span>{s.name}</span>
                    {s.builtin ? (
                      <Badge>builtin</Badge>
                    ) : s.effects.length ? (
                      <Badge tone="warn">{s.effects.length} fx</Badge>
                    ) : null}
                  </div>
                  <div className="text-[9px] text-rf-dim">
                    {s.environment.num_bands} bands · seed {s.environment.seed}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
        <label className="mt-3 block text-[10px] text-rf-dim">
          import scenario JSON
          <input
            type="file"
            accept="application/json"
            className="mt-1 w-full text-[10px]"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) f.text().then(importJson);
              e.target.value = "";
            }}
          />
        </label>
      </Panel>

      {!draft ? (
        <Empty>pick a scenario to view or edit</Empty>
      ) : (
        <div className="flex min-h-0 flex-col gap-2 overflow-auto">
          <Panel
            title={editingBuiltin ? "Built-in (read-only — Save creates a copy)" : "Edit scenario"}
          >
            {msg && (
              <div className="mb-2 rounded border border-rf-accent/40 bg-rf-accent/10 px-2 py-1 text-[11px] text-rf-accent">
                {msg}
              </div>
            )}
            {!canEdit && (
              <div className="mb-2 text-[10px] text-rf-dim">
                read-only — editing needs the operator role
              </div>
            )}
            <label className="mb-2 flex items-center gap-2 text-[11px] text-rf-dim">
              <span className="w-20">name</span>
              <input
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                className="flex-1 rounded border border-rf-border bg-rf-bg px-1.5 py-1 text-[12px] text-rf-text"
              />
            </label>
            <label className="mb-2 flex items-start gap-2 text-[11px] text-rf-dim">
              <span className="w-20 pt-1">description</span>
              <textarea
                rows={2}
                value={draft.description}
                onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                className="flex-1 rounded border border-rf-border bg-rf-bg px-1.5 py-1 text-[11px] text-rf-text"
              />
            </label>

            <div className="grid grid-cols-2 gap-x-3 gap-y-1 sm:grid-cols-3">
              {(
                [
                  ["num_bands", "bands"],
                  ["num_time_slots", "time slots"],
                  ["emitter_density", "emitter density"],
                  ["noise_floor_db", "noise floor dB"],
                  ["snr_min_db", "snr min dB"],
                  ["snr_max_db", "snr max dB"],
                  ["seed", "seed"],
                ] as const
              ).map(([k, label]) => (
                <label
                  key={k}
                  className="flex items-center justify-between gap-1 text-[10px] text-rf-dim"
                >
                  <span>{label}</span>
                  <input
                    type="number"
                    step={k === "emitter_density" ? 0.05 : 1}
                    value={
                      (draft.environment as unknown as Record<string, number>)[k] ?? 0
                    }
                    onChange={(e) => setEnv(k, Number(e.target.value))}
                    className="w-20 rounded border border-rf-border bg-rf-bg px-1 py-0.5 text-right tabular-nums text-rf-text"
                  />
                </label>
              ))}
            </div>
          </Panel>

          <Panel
            title="Simulated EW effects (synthetic — no RF)"
            right={
              canEdit ? (
                <Btn
                  onClick={() =>
                    setDraft({ ...draft, effects: [...draft.effects, blankEffect()] })
                  }
                >
                  + effect
                </Btn>
              ) : undefined
            }
          >
            {draft.effects.length === 0 ? (
              <Empty>no effects — the scenario runs clean</Empty>
            ) : (
              <div className="flex flex-col gap-2">
                {draft.effects.map((fx, i) => (
                  <div
                    key={i}
                    className="rounded border border-rf-border bg-rf-panel2 p-2"
                  >
                    <div className="mb-1 flex items-center gap-2">
                      <select
                        value={fx.kind}
                        onChange={(e) =>
                          setEffect(i, { kind: e.target.value as EWEffectSpec["kind"] })
                        }
                        className="rounded border border-rf-border bg-rf-bg px-1 py-0.5 text-[11px] text-rf-text"
                      >
                        {EFFECT_KINDS.map((k) => (
                          <option key={k} value={k}>
                            {k}
                          </option>
                        ))}
                      </select>
                      <input
                        placeholder="label"
                        value={fx.label}
                        onChange={(e) => setEffect(i, { label: e.target.value })}
                        className="flex-1 rounded border border-rf-border bg-rf-bg px-1.5 py-0.5 text-[11px] text-rf-text"
                      />
                      {canEdit && (
                        <button
                          onClick={() =>
                            setDraft({
                              ...draft,
                              effects: draft.effects.filter((_, j) => j !== i),
                            })
                          }
                          className="text-[11px] text-rf-alert hover:underline"
                        >
                          remove
                        </button>
                      )}
                    </div>
                    <div className="grid grid-cols-3 gap-x-2 gap-y-1 sm:grid-cols-4">
                      {(
                        [
                          ["start_slot", "start"],
                          ["stop_slot", "stop"],
                          ["band_lo", "band lo"],
                          ["band_hi", "band hi"],
                          ["power_db", "power dB"],
                          ...(fx.kind === "swept_jam"
                            ? ([["sweep_rate_bands_per_slot", "sweep/slot"]] as const)
                            : []),
                          ...(fx.kind === "repeater_ghost"
                            ? ([
                                ["source_band", "src band"],
                                ["target_band", "tgt band"],
                                ["delay_slots", "delay"],
                                ["spoof_snr_db", "ghost snr"],
                              ] as const)
                            : []),
                          ...(fx.kind === "spoof_track"
                            ? ([
                                ["target_band", "tgt band"],
                                ["spoof_period_slots", "period"],
                                ["spoof_pulse_slots", "pulse"],
                                ["spoof_snr_db", "snr dB"],
                              ] as const)
                            : []),
                        ] as const
                      ).map(([k, label]) => (
                        <label
                          key={k}
                          className="flex items-center justify-between gap-1 text-[10px] text-rf-dim"
                        >
                          <span>{label}</span>
                          <input
                            type="number"
                            step={k === "sweep_rate_bands_per_slot" ? 0.1 : 1}
                            value={(fx as unknown as Record<string, number>)[k] ?? 0}
                            onChange={(e) =>
                              setEffect(i, { [k]: Number(e.target.value) } as Partial<EWEffectSpec>)
                            }
                            className="w-16 rounded border border-rf-border bg-rf-bg px-1 py-0.5 text-right tabular-nums text-rf-text"
                          />
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Panel>

          <Panel title="Actions">
            <div className="flex flex-wrap gap-1">
              <Btn
                disabled={!canEdit || busy}
                onClick={() =>
                  act(async () => {
                    if (selId && !editingBuiltin) {
                      await api.scenarioUpdate(selId, draft);
                    } else {
                      const s = await api.scenarioCreate(draft);
                      setSelId(s.scenario_id);
                    }
                  }, "saved")
                }
              >
                {selId && !editingBuiltin ? "save" : "save as new"}
              </Btn>
              {selId && (
                <Btn
                  disabled={!canEdit || busy}
                  onClick={() => act(() => api.scenarioDuplicate(selId), "duplicated")}
                >
                  duplicate
                </Btn>
              )}
              {selId && !editingBuiltin && (
                <Btn
                  disabled={!canEdit || busy}
                  onClick={() =>
                    act(async () => {
                      await api.scenarioDelete(selId);
                      setSelId(null);
                      setDraft(null);
                    }, "deleted")
                  }
                >
                  delete
                </Btn>
              )}
              {selected && <Btn onClick={exportJson}>export json</Btn>}
              {selId && (
                <Btn
                  disabled={busy}
                  onClick={() =>
                    act(() => api.scenarioLoad(selId), "loaded into Live Monitor")
                  }
                >
                  ▶ load into Live Monitor
                </Btn>
              )}
            </div>
          </Panel>
        </div>
      )}
    </div>
  );
}
