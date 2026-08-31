import { useCallback, useEffect, useState } from "react";
import {
  api,
  type LibraryEntry,
  type LibraryEntryBody,
  type LibraryRevisionRow,
} from "../api";
import { useAuth } from "../auth";
import { Badge, Btn, Empty, ErrorBanner, Loading, Panel } from "../ui";

const BEHAVIOURS = ["constant", "burst", "periodic", "hopping", "low_duty", "priority"];

function toBody(e: Partial<LibraryEntry>): LibraryEntryBody {
  return {
    name: e.name ?? "new entry",
    behavior: e.behavior ?? "periodic",
    modulation: e.modulation ?? "unknown",
    freq_lo_mhz: e.freq_lo_mhz ?? 0,
    freq_hi_mhz: e.freq_hi_mhz ?? 0,
    home_band: e.home_band ?? 0,
    pri_slots: e.pri_slots ?? 0,
    pri_jitter: e.pri_jitter ?? 0,
    hop_span_bands: e.hop_span_bands ?? 0,
    duty_cycle: e.duty_cycle ?? 0,
    threat: e.threat ?? 0.3,
    notes: e.notes ?? "",
  };
}

export default function Library() {
  const { hasRole, session } = useAuth();
  const canEdit = hasRole("operator") && !session?.demo;

  const [entries, setEntries] = useState<LibraryEntry[] | null>(null);
  const [sel, setSel] = useState<Partial<LibraryEntry> | null>(null);
  const [revs, setRevs] = useState<LibraryRevisionRow[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    api.library().then((r) => setEntries(r.entries)).catch((e) => setErr(String(e)));
  }, []);
  useEffect(refresh, [refresh]);

  function pick(e: LibraryEntry) {
    setSel({ ...e });
    setErr(null);
    api.libraryRevisions(e.entry_id).then((r) => setRevs(r.revisions)).catch(() => setRevs([]));
  }

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

  const set = <K extends keyof LibraryEntry>(k: K, v: LibraryEntry[K]) =>
    setSel((s) => (s ? { ...s, [k]: v } : s));

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 gap-2 overflow-auto p-2 lg:grid-cols-[1fr_1fr]">
      <Panel
        title="Emitter / threat library"
        right={
          <span className="flex items-center gap-2">
            <Badge tone="good">synthetic only</Badge>
            <Btn onClick={refresh}>refresh</Btn>
          </span>
        }
      >
        {err && <ErrorBanner message={err} />}
        {!entries ? (
          <Loading />
        ) : (
          <table className="w-full text-[11px] tabular-nums">
            <thead className="text-rf-dim">
              <tr>
                {["name", "behavior", "mod", "PRI", "threat", "rev"].map((h) => (
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
              {entries.map((e) => (
                <tr
                  key={e.entry_id}
                  onClick={() => pick(e)}
                  className={
                    "cursor-pointer border-t border-rf-grid hover:bg-rf-panel2 " +
                    (sel?.entry_id === e.entry_id ? "bg-rf-accent/10 text-rf-accent" : "")
                  }
                >
                  <td className="text-left">{e.name}</td>
                  <td className="text-right">{e.behavior}</td>
                  <td className="text-right">{e.modulation}</td>
                  <td className="text-right">{e.pri_slots || "—"}</td>
                  <td className="text-right">{e.threat.toFixed(2)}</td>
                  <td className="text-right">{e.revision}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="mt-3">
          <Btn
            disabled={!canEdit}
            onClick={() => {
              setSel({ name: "new entry", behavior: "periodic", threat: 0.4 });
              setRevs([]);
            }}
          >
            + new entry
          </Btn>
        </div>
      </Panel>

      <div className="flex min-h-0 flex-col gap-2 overflow-auto">
        <Panel title={sel?.entry_id ? `Edit — rev ${sel.revision}` : "New entry"}>
          {!sel ? (
            <Empty>select or create an entry</Empty>
          ) : (
            <div className="flex flex-col gap-1.5 text-[11px]">
              <label className="flex items-center gap-2 text-rf-dim">
                <span className="w-24">name</span>
                <input
                  value={sel.name ?? ""}
                  onChange={(e) => set("name", e.target.value)}
                  className="flex-1 rounded border border-rf-border bg-rf-bg px-1.5 py-1 text-rf-text"
                />
              </label>
              <label className="flex items-center gap-2 text-rf-dim">
                <span className="w-24">behavior</span>
                <select
                  value={sel.behavior ?? "periodic"}
                  onChange={(e) => set("behavior", e.target.value)}
                  className="flex-1 rounded border border-rf-border bg-rf-bg px-1.5 py-1 text-rf-text"
                >
                  {BEHAVIOURS.map((b) => (
                    <option key={b} value={b}>
                      {b}
                    </option>
                  ))}
                </select>
              </label>
              {(
                [
                  ["modulation", "text"],
                  ["freq_lo_mhz", "number"],
                  ["freq_hi_mhz", "number"],
                  ["home_band", "number"],
                  ["pri_slots", "number"],
                  ["pri_jitter", "number"],
                  ["hop_span_bands", "number"],
                  ["duty_cycle", "number"],
                  ["threat", "number"],
                ] as const
              ).map(([k, type]) => (
                <label key={k} className="flex items-center gap-2 text-rf-dim">
                  <span className="w-24">{k}</span>
                  <input
                    type={type}
                    step={k === "threat" || k === "duty_cycle" || k === "pri_jitter" ? 0.05 : 1}
                    value={(sel as Record<string, string | number>)[k] ?? (type === "number" ? 0 : "")}
                    onChange={(e) =>
                      set(
                        k,
                        (type === "number" ? Number(e.target.value) : e.target.value) as never,
                      )
                    }
                    className="flex-1 rounded border border-rf-border bg-rf-bg px-1.5 py-1 text-right tabular-nums text-rf-text"
                  />
                </label>
              ))}
              <label className="flex items-start gap-2 text-rf-dim">
                <span className="w-24 pt-1">notes</span>
                <textarea
                  rows={2}
                  value={sel.notes ?? ""}
                  onChange={(e) => set("notes", e.target.value)}
                  className="flex-1 rounded border border-rf-border bg-rf-bg px-1.5 py-1 text-rf-text"
                />
              </label>

              <div className="mt-1 flex gap-1">
                <Btn
                  disabled={!canEdit || busy}
                  onClick={() =>
                    act(async () => {
                      if (sel.entry_id) await api.libraryUpdate(sel.entry_id, toBody(sel));
                      else {
                        const e = await api.libraryCreate(toBody(sel));
                        setSel({ ...e });
                        api.libraryRevisions(e.entry_id).then((r) => setRevs(r.revisions));
                      }
                    })
                  }
                >
                  {sel.entry_id ? "save (new revision)" : "create"}
                </Btn>
                {sel.entry_id && (
                  <Btn
                    disabled={!canEdit || busy}
                    onClick={() =>
                      act(async () => {
                        await api.libraryDelete(sel.entry_id!);
                        setSel(null);
                        setRevs([]);
                      })
                    }
                  >
                    delete (history kept)
                  </Btn>
                )}
              </div>
            </div>
          )}
        </Panel>

        <Panel title="Revision history">
          {revs.length === 0 ? (
            <Empty>no revisions</Empty>
          ) : (
            <table className="w-full text-[10.5px] tabular-nums">
              <thead className="text-rf-dim">
                <tr>
                  <th className="text-left font-normal">rev</th>
                  <th className="text-left font-normal">action</th>
                  <th className="text-left font-normal">actor</th>
                  <th className="text-left font-normal">ts</th>
                  <th className="text-right font-normal">threat</th>
                  <th className="text-right font-normal">PRI</th>
                </tr>
              </thead>
              <tbody>
                {revs.map((r) => (
                  <tr key={r.revision} className="border-t border-rf-grid">
                    <td>{r.revision}</td>
                    <td className="text-rf-accent">{r.action}</td>
                    <td>{r.actor}</td>
                    <td className="text-rf-dim">{r.ts}</td>
                    <td className="text-right">
                      {String((r.snapshot as Record<string, unknown>).threat ?? "")}
                    </td>
                    <td className="text-right">
                      {String((r.snapshot as Record<string, unknown>).pri_slots ?? "")}
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
