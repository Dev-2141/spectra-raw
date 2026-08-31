import { useState } from "react";
import { useAuth } from "./auth";
import { Btn } from "./ui";

export default function LoginScreen() {
  const { login, loginDemo, error } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [demoBusy, setDemoBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await login(username.trim(), password);
    } catch {
      /* error surfaced via context */
    } finally {
      setBusy(false);
    }
  }

  async function skip() {
    setDemoBusy(true);
    try {
      await loginDemo();
    } finally {
      setDemoBusy(false);
    }
  }

  return (
    <div className="grid h-full place-items-center bg-rf-bg text-rf-text">
      <div className="w-[340px] rounded border border-rf-border bg-rf-panel p-5">
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

        <div className="my-3 flex items-center gap-2 text-[10px] text-rf-dim">
          <span className="h-px flex-1 bg-rf-border" />
          or
          <span className="h-px flex-1 bg-rf-border" />
        </div>

        <Btn onClick={skip} disabled={demoBusy}>
          {demoBusy ? "entering…" : "Skip — enter demo (read-only)"}
        </Btn>
        <div className="mt-2 text-[9px] leading-snug text-rf-dim">
          Demo is a temporary presentation aid: read-only, simulation only, no
          hardware or configuration control. Disabled in production.
        </div>
      </div>
    </div>
  );
}
