import { useCallback, useEffect, useState } from "react";
import {
  api,
  type AuditEntry,
  type PlatformUser,
  type Role,
} from "../api";
import { Btn, Empty, ErrorBanner, Loading, Panel } from "../ui";

const ROLES: Role[] = ["viewer", "analyst", "operator", "admin"];

export default function Admin() {
  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 gap-2 overflow-auto p-2 lg:grid-cols-2">
      <Users />
      <ProtectedBands />
      <AuditLog />
    </div>
  );
}

// --------------------------------------------------------------------------- //
function Users() {
  const [users, setUsers] = useState<PlatformUser[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [nu, setNu] = useState({ username: "", password: "", role: "viewer" as Role });

  const load = useCallback(() => {
    setErr(null);
    api
      .users()
      .then((r) => setUsers(r.users))
      .catch((e) => setErr(String(e)));
  }, []);

  useEffect(load, [load]);

  async function act(fn: () => Promise<unknown>) {
    setErr(null);
    try {
      await fn();
      load();
    } catch (e) {
      setErr(String(e));
    }
  }

  return (
    <Panel title="Users" right={<Btn onClick={load}>refresh</Btn>}>
      {err && <ErrorBanner message={err} />}
      {!users ? (
        <Loading />
      ) : (
        <table className="w-full text-[11px]">
          <thead className="text-rf-dim">
            <tr>
              <th className="text-left font-normal">user</th>
              <th className="text-left font-normal">role</th>
              <th className="text-right font-normal">actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.username} className="border-t border-rf-border">
                <td className="py-1">{u.username}</td>
                <td>
                  <select
                    value={u.role}
                    onChange={(e) =>
                      act(() => api.setUserRole(u.username, e.target.value as Role))
                    }
                    className="rounded border border-rf-border bg-rf-bg px-1 py-0.5 text-[11px] text-rf-text"
                  >
                    {ROLES.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="py-1 text-right">
                  <span className="inline-flex gap-1">
                    <Btn
                      onClick={() => {
                        const pw = window.prompt(`New password for ${u.username}`);
                        if (pw) act(() => api.resetUserPassword(u.username, pw));
                      }}
                    >
                      reset pw
                    </Btn>
                    <Btn onClick={() => act(() => api.deleteUser(u.username))}>
                      delete
                    </Btn>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="mt-3 border-t border-rf-border pt-2">
        <div className="mb-1 text-[10px] uppercase tracking-wider text-rf-dim">
          add user
        </div>
        <div className="flex flex-wrap items-center gap-1">
          <input
            placeholder="username"
            value={nu.username}
            onChange={(e) => setNu({ ...nu, username: e.target.value })}
            className="w-28 rounded border border-rf-border bg-rf-bg px-1.5 py-0.5 text-[11px] text-rf-text"
          />
          <input
            placeholder="password"
            type="password"
            value={nu.password}
            onChange={(e) => setNu({ ...nu, password: e.target.value })}
            className="w-28 rounded border border-rf-border bg-rf-bg px-1.5 py-0.5 text-[11px] text-rf-text"
          />
          <select
            value={nu.role}
            onChange={(e) => setNu({ ...nu, role: e.target.value as Role })}
            className="rounded border border-rf-border bg-rf-bg px-1 py-0.5 text-[11px] text-rf-text"
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
          <Btn
            onClick={() =>
              act(async () => {
                await api.createUser(nu.username.trim(), nu.password, nu.role);
                setNu({ username: "", password: "", role: "viewer" });
              })
            }
            disabled={!nu.username || nu.password.length < 6}
          >
            create
          </Btn>
        </div>
      </div>
    </Panel>
  );
}

// --------------------------------------------------------------------------- //
function ProtectedBands() {
  const [bands, setBands] = useState<number[] | null>(null);
  const [raw, setRaw] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .getProtectedBands()
      .then((r) => {
        setBands(r.protected_bands);
        setRaw(r.protected_bands.join(", "));
      })
      .catch((e) => setErr(String(e)));
  }, []);

  useEffect(load, [load]);

  async function save() {
    setErr(null);
    const parsed = raw
      .split(/[,\s]+/)
      .map((s) => parseInt(s, 10))
      .filter((n) => Number.isFinite(n) && n >= 0);
    try {
      const r = await api.setProtectedBands(parsed);
      setBands(r.protected_bands);
      setRaw(r.protected_bands.join(", "));
    } catch (e) {
      setErr(String(e));
    }
  }

  return (
    <Panel title="Protected bands (never-scan)">
      {err && <ErrorBanner message={err} />}
      <p className="mb-2 text-[10px] leading-snug text-rf-dim">
        Any scheduler decision that lands on a protected band is transparently
        redirected to the next-best legal band and the override is audited.
      </p>
      <div className="flex items-center gap-1">
        <input
          value={raw}
          onChange={(e) => setRaw(e.target.value)}
          placeholder="e.g. 0, 1, 12, 30"
          className="flex-1 rounded border border-rf-border bg-rf-bg px-1.5 py-1 text-[11px] text-rf-text"
        />
        <Btn onClick={save}>save</Btn>
      </div>
      <div className="mt-2 text-[11px] text-rf-dim">
        active: {bands && bands.length ? bands.join(", ") : "none"}
      </div>
    </Panel>
  );
}

// --------------------------------------------------------------------------- //
function AuditLog() {
  const [entries, setEntries] = useState<AuditEntry[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [filter, setFilter] = useState({ actor: "", action: "" });

  const load = useCallback(() => {
    setErr(null);
    api
      .audit({
        actor: filter.actor || undefined,
        action: filter.action || undefined,
        limit: 200,
      })
      .then((r) => setEntries(r.entries))
      .catch((e) => setErr(String(e)));
  }, [filter]);

  useEffect(load, [load]);

  return (
    <Panel
      title="Audit log"
      className="lg:col-span-2"
      right={<Btn onClick={load}>refresh</Btn>}
    >
      {err && <ErrorBanner message={err} />}
      <div className="mb-2 flex flex-wrap items-center gap-1">
        <input
          placeholder="actor"
          value={filter.actor}
          onChange={(e) => setFilter({ ...filter, actor: e.target.value })}
          className="w-28 rounded border border-rf-border bg-rf-bg px-1.5 py-0.5 text-[11px] text-rf-text"
        />
        <input
          placeholder="action (supports *)"
          value={filter.action}
          onChange={(e) => setFilter({ ...filter, action: e.target.value })}
          className="w-44 rounded border border-rf-border bg-rf-bg px-1.5 py-0.5 text-[11px] text-rf-text"
        />
      </div>
      {!entries ? (
        <Loading />
      ) : entries.length === 0 ? (
        <Empty>no matching audit entries</Empty>
      ) : (
        <div className="overflow-auto">
          <table className="w-full text-[10.5px] tabular-nums">
            <thead className="text-rf-dim">
              <tr>
                <th className="text-left font-normal">ts</th>
                <th className="text-left font-normal">actor</th>
                <th className="text-left font-normal">action</th>
                <th className="text-left font-normal">target</th>
                <th className="text-left font-normal">mode</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id} className="border-t border-rf-border">
                  <td className="py-0.5 pr-2 text-rf-dim">{e.ts}</td>
                  <td className="pr-2">{e.actor}</td>
                  <td className="pr-2 text-rf-accent">{e.action}</td>
                  <td className="pr-2">{e.target || "—"}</td>
                  <td className="text-rf-dim">{e.mode || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
