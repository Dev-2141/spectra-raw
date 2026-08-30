import { useEffect, useState } from "react";
import type { SimControls } from "./useSim";
import { Badge, Btn, Field, Panel, Select } from "./ui";

const PRESETS: Record<string, { env: Record<string, number>; rcv: Record<string, number> }> = {
  "default 64-band": {
    env: { num_bands: 64, num_time_slots: 1000, emitter_density: 0.15, noise_floor_db: -100, seed: 1234 },
    rcv: { detection_threshold_db: 6, dwell_slots: 1, retune_delay_slots: 1 },
  },
  "dense emitters": {
    env: { num_bands: 64, num_time_slots: 1000, emitter_density: 0.4, noise_floor_db: -100, seed: 7 },
    rcv: { detection_threshold_db: 6, dwell_slots: 1, retune_delay_slots: 1 },
  },
  "sparse / low-duty": {
    env: { num_bands: 96, num_time_slots: 1200, emitter_density: 0.08, noise_floor_db: -100, seed: 21 },
    rcv: { detection_threshold_db: 5, dwell_slots: 1, retune_delay_slots: 1 },
  },
  "noisy spectrum": {
    env: { num_bands: 64, num_time_slots: 1000, emitter_density: 0.2, noise_floor_db: -92, seed: 99 },
    rcv: { detection_threshold_db: 8, dwell_slots: 1, retune_delay_slots: 2 },
  },
};

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
  const [scheduler, setScheduler] = useState("priority");

  // Sync form once from the live state on first load.
  const [synced, setSynced] = useState(false);
  useEffect(() => {
    if (synced || !state) return;
    setBands(state.environment.num_bands);
    setDensity(state.environment.emitter_density);
    setNoise(state.environment.noise_floor_db);
    setSlots(state.environment.num_time_slots);
    setSeed(state.environment.seed);
    setThreshold(state.receiver.detection_threshold_db);
    setDwell(state.receiver.dwell_slots);
    setRetune(state.receiver.retune_delay_slots);
    setScheduler(state.scheduler);
    setSynced(true);
  }, [state, synced]);

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

  const applyPreset = (name: string) => {
    const p = PRESETS[name];
    if (!p) return;
    setBands(p.env.num_bands);
    setSlots(p.env.num_time_slots);
    setDensity(p.env.emitter_density);
    setNoise(p.env.noise_floor_db);
    setSeed(p.env.seed);
    setThreshold(p.rcv.detection_threshold_db);
    setDwell(p.rcv.dwell_slots);
    setRetune(p.rcv.retune_delay_slots);
  };

  const disabled = sim.busy;

  return (
    <aside className="flex w-[260px] shrink-0 flex-col gap-2 overflow-y-auto border-r border-rf-border bg-rf-panel2 p-2">
      <Panel title="Transport">
        <div className="flex flex-wrap gap-1.5">
          <Btn onClick={sim.playing ? sim.pause : sim.play} active={sim.playing} disabled={disabled && !sim.playing}>
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
        <div className="mt-1 flex items-center gap-1.5 text-[10px] text-rf-dim">
          <span>
            t={state?.time_slot ?? 0}/{state?.max_slots ?? 0}
          </span>
          {state?.replay_mode && <Badge tone="scan">replay {state.dataset_id}</Badge>}
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

      <Panel title="Presets">
        <div className="flex flex-col gap-1">
          {Object.keys(PRESETS).map((p) => (
            <Btn key={p} onClick={() => applyPreset(p)} disabled={disabled}>
              {p}
            </Btn>
          ))}
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
      {sim.error && (
        <p className="rounded border border-rf-alert/40 bg-rf-alert/10 p-1 text-[10px] text-rf-alert">
          {sim.error}
        </p>
      )}
    </aside>
  );
}
