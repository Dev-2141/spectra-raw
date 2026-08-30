import { useCallback, useEffect, useState } from "react";
import { api, type TrainingReport } from "../api";
import { LineChart } from "../charts";
import { Badge, Btn, Empty, ErrorBanner, Loading, Panel, Select } from "../ui";

const LEARNERS = ["q_learning", "epsilon_bandit", "ucb_bandit", "thompson", "priority"];

export default function TrainingRuns() {
  const [runs, setRuns] = useState<TrainingReport[]>([]);
  const [scheduler, setScheduler] = useState("q_learning");
  const [episodes, setEpisodes] = useState(12);
  const [steps, setSteps] = useState(600);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openIdx, setOpenIdx] = useState(0);

  const refresh = useCallback(async () => {
    try {
      setRuns((await api.trainingRuns()).runs);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);
  useEffect(() => {
    refresh();
  }, [refresh]);

  const train = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.train(scheduler, episodes, steps);
      setOpenIdx(0);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const run = runs[openIdx];

  return (
    <div className="grid min-h-0 flex-1 grid-cols-[280px_1fr] gap-2 p-2">
      <div className="flex min-h-0 flex-col gap-2">
        <Panel title="New training run">
          <div className="space-y-1.5">
            <Select label="scheduler" value={scheduler} options={LEARNERS} onChange={setScheduler} />
            <label className="flex items-center justify-between text-[11px] text-rf-dim">
              episodes
              <input type="number" value={episodes} min={1} max={100} onChange={(e) => setEpisodes(Number(e.target.value))} className="w-20 rounded border border-rf-border bg-rf-bg px-1.5 py-0.5 text-right text-rf-text" />
            </label>
            <label className="flex items-center justify-between text-[11px] text-rf-dim">
              steps / episode
              <input type="number" value={steps} step={100} min={50} max={20000} onChange={(e) => setSteps(Number(e.target.value))} className="w-20 rounded border border-rf-border bg-rf-bg px-1.5 py-0.5 text-right text-rf-text" />
            </label>
            <Btn active onClick={train} disabled={busy}>
              {busy ? "training…" : "train"}
            </Btn>
            {busy && <Loading label={`training ${episodes} episodes…`} />}
            <p className="text-[10px] text-rf-dim">
              Environment seed varies per episode; the learner keeps its Q-table / arm values across episodes.
            </p>
            {error && <ErrorBanner message={error} onRetry={refresh} />}
          </div>
        </Panel>

        <Panel title={`Run history (${runs.length})`} className="min-h-0 flex-1">
          {runs.length === 0 ? (
            <Empty>no training runs yet</Empty>
          ) : (
            <ul className="space-y-1">
              {runs.map((r, i) => (
                <li
                  key={i}
                  onClick={() => setOpenIdx(i)}
                  className={
                    "cursor-pointer rounded border p-1.5 text-[11px] " +
                    (i === openIdx ? "border-rf-accent bg-rf-accent/5" : "border-rf-border hover:border-rf-dim")
                  }
                >
                  <div className="flex items-center justify-between">
                    <span className="text-rf-text">{r.scheduler}</span>
                    <Badge tone={r.reward_improvement >= 0 ? "good" : "bad"}>
                      Δ {r.reward_improvement >= 0 ? "+" : ""}
                      {r.reward_improvement.toFixed(1)}
                    </Badge>
                  </div>
                  <div className="text-[10px] text-rf-dim">
                    {r.episodes} ep × {r.steps_per_episode} · best ep {r.best_episode}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <Panel title={run ? `${run.scheduler} — ${run.episodes} episodes` : "Training detail"} className="min-h-0">
        {!run ? (
          <Empty>run or select a training job</Empty>
        ) : (
          <div className="flex h-full min-h-0 flex-col gap-2">
            <div className="flex flex-wrap gap-2 text-[11px]">
              <Badge>first avg R {run.first_episode_avg_reward.toFixed(2)}</Badge>
              <Badge>last avg R {run.last_episode_avg_reward.toFixed(2)}</Badge>
              <Badge tone={run.reward_improvement >= 0 ? "good" : "bad"}>
                improvement {run.reward_improvement >= 0 ? "+" : ""}
                {run.reward_improvement.toFixed(2)}
              </Badge>
              <Badge tone="warn">best episode {run.best_episode}</Badge>
            </div>

            <Panel title="Average reward per episode" className="shrink-0">
              <LineChart
                height={170}
                zeroBaseline
                series={[
                  {
                    name: "avg reward",
                    color: "#33d17a",
                    points: run.episode_results.map((e) => e.average_reward),
                  },
                  {
                    name: "P(detection)×10",
                    color: "#3b82f6",
                    points: run.episode_results.map((e) => e.probability_of_detection * 10),
                  },
                ]}
              />
            </Panel>

            <Panel title="Episodes" className="min-h-0 flex-1">
              <table className="w-full text-[11px]">
                <thead className="sticky top-0 bg-rf-panel text-rf-dim">
                  <tr>
                    {["ep", "seed", "avg R", "P(det)", "intercept", "hi-pri", "missed", "epsilon", "Q states", "Q upd"].map((h) => (
                      <th key={h} className={`font-normal ${h === "ep" ? "text-left" : "text-right"}`}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="tabular-nums">
                  {run.episode_results.map((e) => (
                    <tr key={e.episode} className={"border-t border-rf-grid " + (e.episode === run.best_episode ? "text-rf-accent" : "")}>
                      <td>{e.episode}</td>
                      <td className="text-right">{e.seed}</td>
                      <td className="text-right">{e.average_reward.toFixed(2)}</td>
                      <td className="text-right">{e.probability_of_detection.toFixed(3)}</td>
                      <td className="text-right">{e.interception_ratio.toFixed(3)}</td>
                      <td className="text-right">{e.high_priority_detection_rate.toFixed(3)}</td>
                      <td className="text-right">{e.missed_opportunity_count}</td>
                      <td className="text-right">{e.epsilon ?? "—"}</td>
                      <td className="text-right">{e.q_states ?? "—"}</td>
                      <td className="text-right">{e.q_updates ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>
          </div>
        )}
      </Panel>
    </div>
  );
}
