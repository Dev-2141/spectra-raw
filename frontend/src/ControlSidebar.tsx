import { useEffect, useState } from "react";
import { api, type Preset } from "./api";
import type { SimControls } from "./useSim";
import { Badge, Btn, ErrorBanner, Field, Panel, Select } from "./ui";

export default function ControlSidebar({ sim }: { sim: SimControls }) {
  const { state } = sim;
  const [bands, setBands] = useState(64);
  const [density, setDensity] = useState(0.15);
  const [noise, setNoise] = useState(-100);
  const [slots, setSlots] = useState(1000);
  const [seed, setSeed] = useState(1234);
  const [threshold, setThreshold] = useState(6);
  const [dwell, setDwell] = useState(1);
  const [retune, setRetune] = useState(1);
  const [scheduler, setScheduler] = useState("round_robin");
  const [presets, setPresets] = useState<Preset[]>([]);

  useEffect(() => {
    api
      .presets()
      .then((r) => setPresets(r.presets))
      .catch(() => setPresets([]));
  }, []);

  // Mirror the live config into the form whenever it changes server-side
  // (first load, preset applied, dataset loaded, apply & reset).
  useEffect(() => {
    if (!state) return;
    setBands(state.environment.num_bands);
    setDensity(state.environment.emitter_density);
    setNoise(state.environment.noise_floor_db);
    setSlots(state.environment.num_time_slots);
    setSeed(state.environment.seed);
    setThreshold(state.receiver.detection_threshold_db);
    setDwell(state.receiver.dwell_slots);
    setRetune(state.receiver.retune_delay_slots);
  }, [
    state?.environment.num_bands,
    state?.environment.emitter_density,
    state?.environment.noise_floor_db,
    state?.environment.num_time_slots,
    state?.environment.seed,
    state?.receiver.detection_threshold_db,
    state?.receiver.dwell_slots,
    state?.receiver.retune_delay_slots,
    state,
  ]);

  useEffect(() => {
    if (state?.scheduler) setScheduler(state.scheduler);
  }, [state?.scheduler]);

  const applyReset = () =>
    sim.reset({
      environment: {
        num_bands: bands,
        num_time_slots: slots,
        emitter_density: density,
        noise_floor_db: noise,
        seed,
      },
      receiver: {
        detection_threshold_db: threshold,
        dwell_slots: dwell,
        retune_delay_slots: retune,
      },
      scheduler,
    });

  const applyPreset = (name: string) => sim.reset({ preset: name, scheduler });

  const disabled = sim.busy;
  const activePreset = presets.find((p) => p.name === state?.preset);

  return (
    <aside className="flex w-[260px] shrink-0 flex-col gap-2 overflow-y-auto border-r border-rf-border bg-rf-panel2 p-2">
      <Panel title="Transport">
        <div className="flex flex-wrap gap-1.5">
          <Btn
            onClick={sim.playing ? sim.pause : sim.play}
            active={sim.playing}
            disabled={disabled && !sim.playing}
          >
            {sim.playing ? "❚❚ pause" : "▶ play"}
          </Btn>
          <Btn onClick={sim.stepOnce} disabled={disabled}>
            step
          </Btn>
          <Btn onClick={() => sim.runN(100)} disabled={disabled}>
            +100
          </Btn>
          <Btn onClick={() => sim.runN(500)} disabled={disabled}>
            +500
          </Btn>
        </div>
        <label className="mt-2 flex items-center gap-2 text-[11px] text-rf-dim">
          speed
          <input
            type="range"
            min={1}
            max={40}
            value={sim.speed}
            onChange={(e) => sim.setSpeed(Number(e.target.value))}
            className="flex-1 accent-rf-accent"
          />
          <span className="tabular-nums text-rf-text">{sim.speed}/tick</span>
        </label>
        <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px] text-rf-dim">
          <span>
            t={state?.time_slot ?? 0}/{state?.max_slots ?? 0}
          </span>
          {state?.replay_mode && <Badge tone="scan">replay {state.dataset_id}</Badge>}
          {state?.preset && <Badge tone="good">{state.preset}</Badge>}
          {state?.done && <Badge tone="warn">done</Badge>}
        </div>
      </Panel>

      <Panel title="Scheduler">
        <Select
          value={scheduler}
          options={state?.available_schedulers ?? [scheduler]}
          onChange={setScheduler}
        />
        <p className="mt-1 text-[10px] text-rf-dim">
          active: <span className="text-rf-text">{state?.scheduler ?? "—"}</span>
        </p>
      </Panel>

      <Panel title="Scenario presets">
        <div className="flex flex-col gap-1">
          {presets.length === 0 && <span className="text-[10px] text-rf-dim">—</span>}
          {presets.map((p) => (
            <Btn
              key={p.name}
              onClick={() => applyPreset(p.name)}
              disabled={disabled}
              active={state?.preset === p.name}
              title={p.description}
            >
              {p.name}
            </Btn>
          ))}
        </div>
        {activePreset && (
          <p className="mt-1.5 text-[10px] leading-relaxed text-rf-dim">
            {activePreset.description}
          </p>
        )}
      </Panel>

      <Panel title="Environment">
        <div className="space-y-1">
          <Field label="bands" value={bands} onChange={setBands} min={4} max={256} />
          <Field label="time slots" value={slots} onChange={setSlots} step={100} min={50} max={20000} />
          <Field label="emitter density" value={density} onChange={setDensity} step={0.01} min={0} max={1} />
          <Field label="noise floor dB" value={noise} onChange={setNoise} step={1} min={-120} max={-70} />
          <Field label="random seed" value={seed} onChange={setSeed} step={1} />
        </div>
      </Panel>

      <Panel title="Receiver">
        <div className="space-y-1">
          <Field label="detect thresh dB" value={threshold} onChange={setThreshold} step={0.5} min={0} max={30} />
          <Field label="dwell slots" value={dwell} onChange={setDwell} min={1} max={20} />
          <Field label="retune delay" value={retune} onChange={setRetune} min={0} max={20} />
        </div>
      </Panel>

      <div className="sticky bottom-0 flex gap-1.5 bg-rf-panel2 pt-1">
        <Btn onClick={applyReset} disabled={disabled} active>
          apply &amp; reset
        </Btn>
        <Btn onClick={sim.refresh} disabled={disabled}>
          refresh
        </Btn>
      </div>
      {sim.error && <ErrorBanner message={sim.error} onRetry={sim.refresh} />}
    </aside>
  );
}
