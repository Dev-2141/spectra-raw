import { useEffect, useState } from "react";
import { type Role } from "./api";
import { api } from "./api";
import { useAuth } from "./auth";
import { Btn } from "./ui";

const ROLE_BLURB: Record<Role, string> = {
  viewer: "read-only — every screen, no controls",
  analyst: "+ acknowledge/close alerts, run analysis",
  operator: "+ hardware, mode switch, scenarios, tasking, training",
  admin: "+ user management, audit log",
};

export default function LoginScreen() {
  const { login, loginDemo, quickLogin, error } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<string | null>(null);
  const [cfg, setCfg] = useState<{
    quick_login_enabled: boolean;
    demo_enabled: boolean;
    roles: Role[];
    seed_convention: string | null;
  } | null>(null);

  useEffect(() => {
    api.authConfig().then(setCfg).catch(() => setCfg(null));
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await login(username.trim(), password);
    } catch {
      /* surfaced via context */
    } finally {
      setBusy(false);
    }
  }

  async function quick(kind: string, fn: () => Promise<void>) {
    setPending(kind);
    try {
      await fn();
    } catch {
      /* surfaced via context */
    } finally {
      setPending(null);
    }
  }

  const showQuick = cfg?.quick_login_enabled;
  const showDemo = cfg?.demo_enabled;

  return (
    <div className="grid h-full place-items-center overflow-auto bg-rf-bg text-rf-text">
      <div className="w-[380px] rounded border border-rf-border bg-rf-panel p-5">
        <div className="mb-1 text-[13px] font-bold tracking-[0.22em] text-rf-accent">
          SPECTRA-SCAN&nbsp;AI
        </div>
        <div className="mb-4 text-[10px] text-rf-dim">
          Adaptive Smart Scan Scheduler · sign in to continue
        </div>

        <form onSubmit={submit} className="flex flex-col gap-2">
          <label className="flex flex-col gap-1 text-[11px] text-rf-dim">
            username
            <input
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="rounded border border-rf-border bg-rf-bg px-2 py-1 text-[12px] text-rf-text focus:border-rf-accent focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1 text-[11px] text-rf-dim">
            password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="rounded border border-rf-border bg-rf-bg px-2 py-1 text-[12px] text-rf-text focus:border-rf-accent focus:outline-none"
            />
          </label>

          {error && (
            <div className="rounded border border-rf-alert/40 bg-rf-alert/10 px-2 py-1 text-[11px] text-rf-alert">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={busy || !username || !password}
            className="mt-1 rounded border border-rf-accent bg-rf-accent/10 px-2 py-1.5 text-[12px] text-rf-accent transition hover:bg-rf-accent/20 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy ? "signing in…" : "sign in"}
          </button>
        </form>

        {(showQuick || showDemo) && (
          <>
            <div className="my-3 flex items-center gap-2 text-[10px] text-rf-dim">
              <span className="h-px flex-1 bg-rf-border" />
              quick sign-in · presentation only
              <span className="h-px flex-1 bg-rf-border" />
            </div>

            {showQuick && (
              <div className="flex flex-col gap-1">
                {(["viewer", "analyst", "operator", "admin"] as Role[]).map((r) => (
                  <button
                    key={r}
                    disabled={pending !== null}
                    onClick={() => quick(r, () => quickLogin(r))}
                    className="flex items-center justify-between rounded border border-rf-border bg-rf-panel2 px-2 py-1 text-left text-[11px] transition hover:border-rf-accent disabled:opacity-40"
                  >
                    <span className="font-medium text-rf-text">
                      {pending === r ? "entering…" : `enter as ${r}`}
                    </span>
                    <span className="ml-2 text-[9px] text-rf-dim">{ROLE_BLURB[r]}</span>
                  </button>
                ))}
              </div>
            )}

            {showDemo && (
              <div className="mt-2">
                <Btn
                  disabled={pending !== null}
                  onClick={() => quick("demo", loginDemo)}
                >
                  {pending === "demo" ? "entering…" : "read-only demo (no account)"}
                </Btn>
              </div>
            )}

            <div className="mt-2 text-[9px] leading-snug text-rf-dim">
              Quick sign-in logs into a real seeded account
              {cfg?.seed_convention ? ` (${cfg.seed_convention})` : ""}. It bypasses
              password entry, not the user store or RBAC, and is hard-disabled when
              the server runs in production or without seed users. The demo session
              is read-only and simulation-only.
            </div>
          </>
        )}

        {cfg && !showQuick && !showDemo && (
          <div className="mt-3 text-[9px] text-rf-dim">
            Production mode: quick sign-in and demo are disabled. Use issued
            credentials.
          </div>
        )}
      </div>
    </div>
  );
}
