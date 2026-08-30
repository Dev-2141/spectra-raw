import { useCallback, useEffect, useState } from "react";
import { api, type DatasetMeta } from "../api";
import { Waterfall } from "../charts";
import { Badge, Btn, Empty, ErrorBanner, Field, Loading, Panel } from "../ui";
import type { SimControls } from "../useSim";

export default function DatasetLab({ sim }: { sim: SimControls }) {
  const [list, setList] = useState<DatasetMeta[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [bands, setBands] = useState(64);
  const [slots, setSlots] = useState(1000);
  const [density, setDensity] = useState(0.15);
  const [seed, setSeed] = useState(2025);
  const [sel, setSel] = useState<DatasetMeta | null>(null);
  const [preview, setPreview] = useState<{ power_db: number[][] } | null>(null);

  const refresh = useCallback(async () => {
    try {
      setList((await api.datasetList()).datasets);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);
  useEffect(() => {
    refresh();
  }, [refresh]);

  const wrap = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const generate = () =>
    wrap(async () => {
      await api.datasetGenerate(name || undefined, {
        num_bands: bands,
        num_time_slots: slots,
        emitter_density: density,
        seed,
      });
      setName("");
      await refresh();
    });

  const select = (d: DatasetMeta) =>
    wrap(async () => {
      setSel(d);
      setPreview(await api.datasetPreview(d.dataset_id));
    });

  const load = (d: DatasetMeta) =>
    wrap(async () => {
      await api.datasetLoad(d.dataset_id, sim.state?.scheduler);
      await sim.refresh();
    });

  return (
    <div className="grid min-h-0 flex-1 grid-cols-[300px_1fr] gap-2 p-2">
      <div className="flex min-h-0 flex-col gap-2 overflow-y-auto">
        <Panel title="Generate dataset">
          <div className="space-y-1">
            <label className="flex items-center justify-between gap-2 text-[11px] text-rf-dim">
              <span>name</span>
              <input
                value={name}
                placeholder="auto"
                onChange={(e) => setName(e.target.value)}
                className="w-32 rounded border border-rf-border bg-rf-bg px-1.5 py-0.5 text-rf-text"
              />
            </label>
            <Field label="bands" value={bands} onChange={setBands} min={4} max={256} />
            <Field label="time slots" value={slots} onChange={setSlots} step={100} min={50} max={20000} />
            <Field label="emitter density" value={density} onChange={setDensity} step={0.01} min={0} max={1} />
            <Field label="seed" value={seed} onChange={setSeed} />
          </div>
          <div className="mt-2">
            <Btn active onClick={generate} disabled={busy}>
              {busy ? "working…" : "generate"}
            </Btn>
          </div>
          {error && (
            <div className="mt-1">
              <ErrorBanner message={error} onRetry={refresh} />
            </div>
          )}
        </Panel>

        <Panel title={`Datasets (${list.length})`} className="min-h-0 flex-1">
          {list.length === 0 ? (
            <Empty>no datasets yet</Empty>
          ) : (
            <ul className="space-y-1">
              {list.map((d) => (
                <li
                  key={d.dataset_id}
                  className={
                    "cursor-pointer rounded border p-1.5 text-[11px] " +
                    (sel?.dataset_id === d.dataset_id
                      ? "border-rf-accent bg-rf-accent/5"
                      : "border-rf-border hover:border-rf-dim")
                  }
                  onClick={() => select(d)}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-rf-text">{d.name}</span>
                    {sim.state?.dataset_id === d.dataset_id && <Badge tone="scan">loaded</Badge>}
                  </div>
                  <div className="text-[10px] text-rf-dim">
                    {d.number_of_bands}×{d.number_of_time_slots} · occ{" "}
                    {(d.stats.occupancy_percentage * 100).toFixed(1)}% · {d.emitters.length} emitters
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <Panel title={sel ? `Dataset — ${sel.name}` : "Dataset detail"} className="min-h-0">
        {!sel ? (
          <Empty>select a dataset</Empty>
        ) : (
          <div className="flex h-full min-h-0 flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <Btn active onClick={() => load(sel)} disabled={busy}>
                load into simulation
              </Btn>
              <a className="text-[11px] text-rf-scan hover:text-rf-accent" href={`/api/dataset/${sel.dataset_id}`} target="_blank" rel="noreferrer">
                ↗ meta.json
              </a>
              <span className="text-[10px] text-rf-dim">id {sel.dataset_id} · {sel.created_at}</span>
            </div>

            <div className="grid grid-cols-2 gap-2 text-[11px] md:grid-cols-4">
              <Kv k="occupancy %" v={(sel.stats.occupancy_percentage * 100).toFixed(2)} />
              <Kv k="sparsity" v={sel.stats.sparsity_score.toFixed(3)} />
              <Kv k="active bands" v={sel.stats.active_band_count} />
              <Kv k="active slots" v={sel.stats.active_time_count} />
              <Kv k="avg SNR dB" v={sel.stats.average_snr_db.toFixed(1)} />
              <Kv k="emitters" v={sel.emitters.length} />
              <Kv k="threat hi" v={sel.stats.threat_distribution["high(>=0.7)"] ?? 0} />
              <Kv k="threat lo" v={sel.stats.threat_distribution["low(<0.3)"] ?? 0} />
            </div>

            <div className="flex flex-wrap gap-1.5 text-[10px] text-rf-dim">
              {Object.entries(sel.stats.emitter_type_distribution).map(([k, v]) => (
                <Badge key={k}>
                  {k} ×{v}
                </Badge>
              ))}
            </div>

            <Panel title="Preview heatmap — power (band × time, down-sampled)" className="min-h-0 flex-1">
              {preview ? (
                <Waterfall power={preview.power_db} startSlot={0} scanPath={[]} height={300} />
              ) : (
                <Loading label="loading preview…" />
              )}
            </Panel>
          </div>
        )}
      </Panel>
    </div>
  );
}

function Kv({ k, v }: { k: string; v: string | number }) {
  return (
    <div className="rounded border border-rf-border bg-rf-panel2 px-2 py-1">
      <div className="text-[9px] uppercase tracking-wider text-rf-dim">{k}</div>
      <div className="tabular-nums text-rf-text">{v}</div>
    </div>
  );
}
