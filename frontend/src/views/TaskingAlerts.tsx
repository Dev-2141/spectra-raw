import { useCallback, useEffect, useState } from "react";
import {
  api,
  type AlertItem,
  type AlertRuleItem,
  type WatchListItem,
} from "../api";
import { useAuth } from "../auth";
import { Badge, Btn, Empty, ErrorBanner, Loading, Panel } from "../ui";

const SEV_TONE: Record<string, "dim" | "warn" | "bad"> = {
  info: "dim",
  warn: "warn",
  critical: "bad",
};

export default function TaskingAlerts() {
  const { hasRole, session } = useAuth();
  const canTask = hasRole("operator") && !session?.demo;
  const canAck = hasRole("analyst") && !session?.demo;

  const [watch, setWatch] = useState<WatchListItem[] | null>(null);
  const [rules, setRules] = useState<AlertRuleItem[] | null>(null);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [filter, setFilter] = useState<"open" | "all">("open");
  const [err, setErr] = useState<string | null>(null);

  const refresh = useCallback(() => {
    api.alerts(filter === "open" ? "open" : undefined)
      .then((r) => setAlerts(r.alerts))
      .catch((e) => setErr(String(e)));
  }, [filter]);

  useEffect(() => {
    api.watchLists().then((r) => setWatch(r.watch_lists)).catch((e) => setErr(String(e)));
    api.alertRules().then((r) => setRules(r.alert_rules)).catch(() => undefined);
  }, []);

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, 3000);
    return () => window.clearInterval(id);
  }, [refresh]);

  async function saveWatch(next: WatchListItem[]) {
    setErr(null);
    try {
      setWatch((await api.setWatchLists(next)).watch_lists);
    } catch (e) {
      setErr(String(e));
    }
  }
  async function saveRules(next: AlertRuleItem[]) {
    setErr(null);
    try {
      setRules((await api.setAlertRules(next)).alert_rules);
    } catch (e) {
      setErr(String(e));
    }
  }
  async function setAlert(id: string, action: "ack" | "close") {
    try {
      await (action === "ack" ? api.ackAlert(id) : api.closeAlert(id));
      refresh();
    } catch (e) {
      setErr(String(e));
    }
  }

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 gap-2 overflow-auto p-2 lg:grid-cols-[360px_1fr]">
      <div className="flex min-h-0 flex-col gap-2 overflow-auto">
        <Panel
          title="Watch lists (priority weights)"
          right={
            canTask ? (
              <Btn
                onClick={() =>
                  saveWatch([
                    ...(watch ?? []),
                    { id: "", name: "watch", band_lo: 0, band_hi: 4, weight: 2, enabled: true },
                  ])
                }
              >
                + add
              </Btn>
            ) : undefined
          }
        >
          {err && <ErrorBanner message={err} />}
          {!watch ? (
            <Loading />
          ) : watch.length === 0 ? (
            <Empty>no watch lists — scheduler treats all bands equally</Empty>
          ) : (
            <div className="flex flex-col gap-1">
              {watch.map((w, i) => (
                <div
                  key={w.id || i}
                  className="rounded border border-rf-border bg-rf-panel2 p-1.5"
                >
                  <div className="flex items-center gap-1 text-[11px]">
                    <input
                      value={w.name}
                      disabled={!canTask}
                      onChange={(e) =>
                        setWatch(watch.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))
                      }
                      className="w-24 rounded border border-rf-border bg-rf-bg px-1 py-0.5 text-rf-text"
                    />
                    {(["band_lo", "band_hi", "weight"] as const).map((k) => (
                      <label key={k} className="flex items-center gap-0.5 text-[10px] text-rf-dim">
                        {k.replace("band_", "b")}
                        <input
                          type="number"
                          step={k === "weight" ? 0.5 : 1}
                          value={w[k]}
                          disabled={!canTask}
                          onChange={(e) =>
                            setWatch(
                              watch.map((x, j) =>
                                j === i ? { ...x, [k]: Number(e.target.value) } : x,
                              ),
                            )
                          }
                          className="w-12 rounded border border-rf-border bg-rf-bg px-1 py-0.5 text-right tabular-nums text-rf-text"
                        />
                      </label>
                    ))}
                    <button
                      disabled={!canTask}
                      onClick={() => saveWatch(watch.filter((_, j) => j !== i))}
                      className="text-[10px] text-rf-alert hover:underline disabled:opacity-40"
                    >
                      del
                    </button>
                  </div>
                </div>
              ))}
              <Btn disabled={!canTask} onClick={() => saveWatch(watch)}>
                save watch lists
              </Btn>
            </div>
          )}
        </Panel>

        <Panel title="Alert rules">
          {!rules ? (
            <Loading />
          ) : (
            <div className="flex flex-col gap-1 text-[11px]">
              {rules.map((r, i) => (
                <label
                  key={r.id}
                  className="flex items-center justify-between gap-2 rounded border border-rf-border bg-rf-panel2 px-2 py-1"
                >
                  <span className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={r.enabled}
                      disabled={!canTask}
                      onChange={(e) =>
                        saveRules(
                          rules.map((x, j) =>
                            j === i ? { ...x, enabled: e.target.checked } : x,
                          ),
                        )
                      }
                    />
                    {r.kind}
                  </span>
                  <span className="flex items-center gap-1">
                    <Badge tone={SEV_TONE[r.severity] ?? "dim"}>{r.severity}</Badge>
                    {["priority_hit", "library_match"].includes(r.kind) && (
                      <input
                        type="number"
                        step={0.05}
                        value={r.threshold}
                        disabled={!canTask}
                        onChange={(e) =>
                          saveRules(
                            rules.map((x, j) =>
                              j === i ? { ...x, threshold: Number(e.target.value) } : x,
                            ),
                          )
                        }
                        className="w-14 rounded border border-rf-border bg-rf-bg px-1 py-0.5 text-right tabular-nums text-rf-text"
                      />
                    )}
                  </span>
                </label>
              ))}
            </div>
          )}
        </Panel>
      </div>

      <Panel
        title="Alert feed"
        right={
          <span className="flex items-center gap-2 text-[10px]">
            <button
              onClick={() => setFilter(filter === "open" ? "all" : "open")}
              className="rounded border border-rf-border px-1.5 py-0.5 text-rf-dim hover:text-rf-accent"
            >
              {filter === "open" ? "showing open" : "showing all"}
            </button>
            <Btn onClick={refresh}>refresh</Btn>
          </span>
        }
      >
        {alerts.length === 0 ? (
          <Empty>no alerts</Empty>
        ) : (
          <div className="flex flex-col gap-1">
            {alerts.map((a) => (
              <div
                key={a.alert_id}
                className={
                  "flex items-center justify-between gap-2 rounded border px-2 py-1 text-[11px] " +
                  (a.state === "closed"
                    ? "border-rf-border opacity-50"
                    : a.severity === "critical"
                      ? "border-rf-alert/50"
                      : a.severity === "warn"
                        ? "border-rf-warn/40"
                        : "border-rf-border")
                }
              >
                <span className="flex items-center gap-2">
                  <Badge tone={SEV_TONE[a.severity] ?? "dim"}>{a.rule_kind}</Badge>
                  <span>{a.detail}</span>
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="text-rf-dim">{a.state}</span>
                  {a.state === "open" && (
                    <button
                      disabled={!canAck}
                      onClick={() => setAlert(a.alert_id, "ack")}
                      className="rounded border border-rf-border px-1.5 py-0.5 text-rf-dim hover:text-rf-accent disabled:opacity-40"
                    >
                      ack
                    </button>
                  )}
                  {a.state !== "closed" && (
                    <button
                      disabled={!canAck}
                      onClick={() => setAlert(a.alert_id, "close")}
                      className="rounded border border-rf-border px-1.5 py-0.5 text-rf-dim hover:text-rf-accent disabled:opacity-40"
                    >
                      close
                    </button>
                  )}
                </span>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
