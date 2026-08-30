import { useEffect, useRef } from "react";

export const SERIES_COLORS = [
  "#33d17a",
  "#3b82f6",
  "#f0b429",
  "#ef476f",
  "#a78bfa",
  "#22d3ee",
  "#f97316",
];

// --------------------------------------------------------------------------- //
// Spectrum: power vs band
// --------------------------------------------------------------------------- //
export function SpectrumChart({
  power,
  active,
  threshold,
  currentBand,
  height = 150,
}: {
  power: number[];
  active: number[];
  threshold: number;
  currentBand: number;
  height?: number;
}) {
  const n = power.length || 1;
  const lo = Math.min(...power, threshold) - 3;
  const hi = Math.max(...power, threshold) + 3;
  const y = (p: number) => height - ((p - lo) / (hi - lo || 1)) * height;
  const bw = 100 / n;

  return (
    <svg
      viewBox={`0 0 100 ${height}`}
      preserveAspectRatio="none"
      className="h-full w-full"
    >
      {[0.25, 0.5, 0.75].map((f) => (
        <line
          key={f}
          x1={0}
          x2={100}
          y1={height * f}
          y2={height * f}
          stroke="#16202e"
          strokeWidth={0.3}
        />
      ))}
      {power.map((p, i) => (
        <rect
          key={i}
          x={i * bw + bw * 0.08}
          y={y(p)}
          width={bw * 0.84}
          height={Math.max(0.5, height - y(p))}
          fill={
            i === currentBand
              ? "#3b82f6"
              : active[i]
                ? "#33d17a"
                : "#243449"
          }
        />
      ))}
      {active.map((a, i) =>
        a ? (
          <circle key={`m${i}`} cx={i * bw + bw / 2} cy={y(power[i]) - 2} r={0.7} fill="#33d17a" />
        ) : null,
      )}
      <line
        x1={0}
        x2={100}
        y1={y(threshold)}
        y2={y(threshold)}
        stroke="#f0b429"
        strokeWidth={0.5}
        strokeDasharray="1.5 1.5"
      />
      {currentBand >= 0 && currentBand < n && (
        <rect
          x={currentBand * bw}
          y={0}
          width={bw}
          height={height}
          fill="#3b82f6"
          opacity={0.12}
        />
      )}
    </svg>
  );
}

// --------------------------------------------------------------------------- //
// Waterfall heatmap (canvas) with scan-path overlay
// --------------------------------------------------------------------------- //
type PathRow = {
  time_slot: number;
  scanned_band: number;
  detected: boolean;
  false_alarm: boolean;
  true_active: boolean;
};

export function Waterfall({
  power,
  startSlot,
  scanPath,
  height = 240,
}: {
  power: number[][];
  startSlot: number;
  scanPath: PathRow[];
  height?: number;
}) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const rows = power.length;
    const cols = rows ? power[power.length - 1].length : 0;
    if (!rows || !cols) return;

    const cw = canvas.clientWidth || 640;
    const scale = 3; // internal supersample for crispness
    canvas.width = cols * scale;
    canvas.height = rows * scale;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let min = Infinity;
    let max = -Infinity;
    for (const row of power)
      for (const v of row) {
        if (v < min) min = v;
        if (v > max) max = v;
      }
    const span = max - min || 1;

    for (let r = 0; r < rows; r++) {
      const row = power[r];
      for (let c = 0; c < cols; c++) {
        const t = (row[c] - min) / span;
        const rr = Math.round(8 + t * 40);
        const gg = Math.round(20 + t * 200);
        const bb = Math.round(45 + t * 90);
        ctx.fillStyle = `rgb(${rr},${gg},${bb})`;
        ctx.fillRect(c * scale, r * scale, scale, scale);
      }
    }

    for (const p of scanPath) {
      const r = p.time_slot - startSlot;
      if (r < 0 || r >= rows) continue;
      ctx.fillStyle = p.detected
        ? "#5eead4"
        : p.false_alarm
          ? "#ef476f"
          : p.true_active
            ? "#f0b429"
            : "rgba(59,130,246,0.5)";
      ctx.fillRect(p.scanned_band * scale, r * scale, scale, scale);
    }
    void cw;
  }, [power, startSlot, scanPath]);

  return (
    <canvas
      ref={ref}
      style={{ height, imageRendering: "pixelated" }}
      className="w-full rounded"
    />
  );
}

// --------------------------------------------------------------------------- //
// Multi-series line chart
// --------------------------------------------------------------------------- //
export type LineSeries = { name: string; color: string; points: number[]; x?: number[] };

export function LineChart({
  series,
  height = 180,
  yFormat = (v) => v.toFixed(2),
  zeroBaseline = false,
}: {
  series: LineSeries[];
  height?: number;
  yFormat?: (v: number) => string;
  zeroBaseline?: boolean;
}) {
  const W = 1000; // internal units; stretched to container width
  const padR = 6;

  const allY = series.flatMap((s) => s.points);
  if (allY.length === 0) return null;
  let minY = Math.min(...allY);
  let maxY = Math.max(...allY);
  if (zeroBaseline) {
    minY = Math.min(minY, 0);
    maxY = Math.max(maxY, 0);
  }
  if (maxY - minY < 1e-9) maxY = minY + 1;

  const maxLen = Math.max(...series.map((s) => s.points.length));
  const py = (v: number) => (1 - (v - minY) / (maxY - minY)) * height;
  const ticks = [1, 0.75, 0.5, 0.25, 0].map((f) => minY + f * (maxY - minY));

  return (
    <div className="flex flex-col">
      <div className="mb-1 flex flex-wrap gap-x-3 gap-y-0.5">
        {series.map((s) => (
          <span key={s.name} className="flex items-center gap-1 text-[10px] text-rf-dim">
            <span className="inline-block h-1.5 w-3" style={{ background: s.color }} />
            {s.name}
          </span>
        ))}
      </div>
      <div className="flex">
        {/* y-axis labels as HTML so they don't stretch */}
        <div
          className="flex w-10 shrink-0 flex-col justify-between pr-1 text-right text-[9px] tabular-nums text-rf-dim"
          style={{ height }}
        >
          {ticks.map((tv, i) => (
            <span key={i} className="-my-1 leading-none">
              {yFormat(tv)}
            </span>
          ))}
        </div>
        <svg
          viewBox={`0 0 ${W} ${height}`}
          preserveAspectRatio="none"
          className="flex-1 border-l border-rf-border"
          style={{ height }}
        >
          {ticks.map((tv, i) => (
            <line
              key={i}
              x1={0}
              x2={W - padR}
              y1={py(tv)}
              y2={py(tv)}
              stroke="#16202e"
              strokeWidth={1}
              vectorEffect="non-scaling-stroke"
            />
          ))}
          {zeroBaseline && minY < 0 && maxY > 0 && (
            <line
              x1={0}
              x2={W - padR}
              y1={py(0)}
              y2={py(0)}
              stroke="#2c3b4f"
              strokeWidth={1}
              vectorEffect="non-scaling-stroke"
            />
          )}
          {series.map((s) => {
            const len = s.points.length;
            const lastX = s.x ? s.x[len - 1] || 1 : len - 1 || 1;
            const d = s.points
              .map((v, i) => {
                const xr = s.x ? s.x[i] / lastX : i / lastX;
                const xi = xr * (W - padR);
                return `${i === 0 ? "M" : "L"}${xi.toFixed(1)},${py(v).toFixed(1)}`;
              })
              .join(" ");
            return (
              <path
                key={s.name}
                d={d}
                fill="none"
                stroke={s.color}
                strokeWidth={1.5}
                vectorEffect="non-scaling-stroke"
              />
            );
          })}
        </svg>
      </div>
      <div className="flex justify-between pl-10 text-[9px] text-rf-dim">
        <span>start</span>
        <span>{maxLen} pts</span>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Vertical bar chart (one metric across categories)
// --------------------------------------------------------------------------- //
export function BarChart({
  data,
  height = 150,
  valueFormat = (v) => v.toFixed(2),
}: {
  data: { label: string; value: number; color?: string }[];
  height?: number;
  valueFormat?: (v: number) => string;
}) {
  if (data.length === 0) return null;
  const max = Math.max(...data.map((d) => d.value), 1e-9);
  const min = Math.min(0, ...data.map((d) => d.value));
  const span = max - min || 1;
  return (
    <div className="flex items-end gap-1.5" style={{ height }}>
      {data.map((d) => {
        const h = ((d.value - min) / span) * (height - 22);
        return (
          <div key={d.label} className="flex flex-1 flex-col items-center justify-end gap-0.5">
            <span className="tabular-nums text-[9px] text-rf-dim">{valueFormat(d.value)}</span>
            <div
              className="w-full rounded-t"
              style={{ height: Math.max(2, h), background: d.color ?? "#3b82f6" }}
            />
            <span className="w-full truncate text-center text-[9px] text-rf-dim" title={d.label}>
              {d.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export function Sparkline({ points, color = "#33d17a", height = 24 }: { points: number[]; color?: string; height?: number }) {
  if (points.length < 2) return null;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const d = points
    .map((v, i) => `${i === 0 ? "M" : "L"}${(i / (points.length - 1)) * 100},${height - ((v - min) / span) * height}`)
    .join(" ");
  return (
    <svg viewBox={`0 0 100 ${height}`} preserveAspectRatio="none" className="w-full" style={{ height }}>
      <path d={d} fill="none" stroke={color} strokeWidth={1} />
    </svg>
  );
}
