import type { ChangeEvent, ReactNode } from "react";

export function Panel({
  title,
  right,
  children,
  className = "",
}: {
  title?: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`flex min-h-0 flex-col rounded border border-rf-border bg-rf-panel ${className}`}
    >
      {title && (
        <div className="flex shrink-0 items-center justify-between border-b border-rf-border px-2 py-1">
          <span className="text-[10px] uppercase tracking-wider text-rf-dim">
            {title}
          </span>
          {right}
        </div>
      )}
      <div className="min-h-0 flex-1 overflow-auto p-2 text-[12px]">{children}</div>
    </section>
  );
}

export function Btn({
  children,
  onClick,
  disabled,
  active,
  title,
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  active?: boolean;
  title?: string;
}) {
  return (
    <button
      title={title}
      onClick={onClick}
      disabled={disabled}
      className={
        "rounded border px-2 py-1 text-[11px] transition disabled:cursor-not-allowed disabled:opacity-40 " +
        (active
          ? "border-rf-accent bg-rf-accent/10 text-rf-accent"
          : "border-rf-border bg-rf-panel2 text-rf-text hover:border-rf-accent hover:text-rf-accent")
      }
    >
      {children}
    </button>
  );
}

export function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string | number;
  hint?: string;
  tone?: "good" | "bad" | "warn" | "scan";
}) {
  const color =
    tone === "good"
      ? "text-rf-accent"
      : tone === "bad"
        ? "text-rf-alert"
        : tone === "warn"
          ? "text-rf-warn"
          : tone === "scan"
            ? "text-rf-scan"
            : "text-rf-text";
  return (
    <div className="rounded border border-rf-border bg-rf-panel2 px-2 py-1.5">
      <div className="text-[9px] uppercase tracking-wider text-rf-dim">{label}</div>
      <div className={`tabular-nums text-[15px] leading-tight ${color}`}>{value}</div>
      {hint && <div className="text-[9px] text-rf-dim">{hint}</div>}
    </div>
  );
}

export function Field({
  label,
  value,
  onChange,
  step = 1,
  min,
  max,
  type = "number",
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  step?: number;
  min?: number;
  max?: number;
  type?: string;
}) {
  return (
    <label className="flex items-center justify-between gap-2 text-[11px] text-rf-dim">
      <span>{label}</span>
      <input
        type={type}
        value={value}
        step={step}
        min={min}
        max={max}
        onChange={(e: ChangeEvent<HTMLInputElement>) =>
          onChange(Number(e.target.value))
        }
        className="w-24 rounded border border-rf-border bg-rf-bg px-1.5 py-0.5 text-right tabular-nums text-rf-text focus:border-rf-accent focus:outline-none"
      />
    </label>
  );
}

export function Select({
  label,
  value,
  options,
  onChange,
}: {
  label?: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-[11px] text-rf-dim">
      {label && <span>{label}</span>}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="flex-1 rounded border border-rf-border bg-rf-bg px-1.5 py-1 text-[12px] text-rf-text focus:border-rf-accent focus:outline-none"
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </label>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="grid h-full min-h-[60px] place-items-center text-[11px] text-rf-dim">
      {children}
    </div>
  );
}

export function Badge({
  children,
  tone = "dim",
}: {
  children: ReactNode;
  tone?: "dim" | "good" | "bad" | "warn" | "scan";
}) {
  const map = {
    dim: "border-rf-border text-rf-dim",
    good: "border-rf-accent/50 text-rf-accent",
    bad: "border-rf-alert/50 text-rf-alert",
    warn: "border-rf-warn/50 text-rf-warn",
    scan: "border-rf-scan/50 text-rf-scan",
  } as const;
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[10px] ${map[tone]}`}>
      {children}
    </span>
  );
}

export function OutcomeTag({ outcome }: { outcome: string }) {
  const tone =
    outcome === "hit"
      ? "good"
      : outcome === "false_alarm"
        ? "bad"
        : outcome === "miss"
          ? "warn"
          : "dim";
  return <Badge tone={tone}>{outcome}</Badge>;
}
