import { useRef, useState } from "react";
import type { ElevationComparison } from "../api/types";

interface Props {
  /** Every provider id in registry order, so a provider keeps its colour whichever are compared. */
  providerOrder: string[];
  pending: boolean;
  error: string | null;
  result: ElevationComparison | null;
  onClose: () => void;
}

// Categorical slots 1-3 (blue, orange, aqua), checked for colour-blind separation.
// The recorded heights are the reference, so they get neutral ink rather than a hue.
const SERIES = ["#2a78d6", "#eb6834", "#1baf7a"];
const OVERFLOW = "#9ca3af";
const RECORDED = "#374151";

const W = 1000;
const H = 280;
const PAD_L = 48;
const PAD_R = 12;
const PAD_T = 12;
const PAD_B = 28;

type Mode = "heights" | "difference";

interface Series {
  id: string;
  label: string;
  color: string;
  values: (number | null)[];
  dashed?: boolean;
}

/** Round-number ticks spanning lo..hi. */
function ticks(lo: number, hi: number, count = 5): number[] {
  const raw = (hi - lo) / Math.max(1, count - 1);
  const mag = 10 ** Math.floor(Math.log10(raw || 1));
  const step = [1, 2, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(Math.round(v * 100) / 100);
  return out;
}

/** An SVG path that lifts the pen over gaps rather than bridging them. */
function pathOf(xs: number[], ys: (number | null)[]): string {
  let d = "";
  let pen = false;
  ys.forEach((y, k) => {
    if (y == null) {
      pen = false;
      return;
    }
    d += `${pen ? "L" : "M"}${xs[k].toFixed(1)},${y.toFixed(1)}`;
    pen = true;
  });
  return d;
}

const fmt = (v: number | null | undefined, signed = false) =>
  v == null ? "-" : `${signed && v > 0 ? "+" : ""}${v.toFixed(1)}`;

export default function ElevationCompare({ providerOrder, pending, error, result, onClose }: Props) {
  const [mode, setMode] = useState<Mode>("heights");
  const [hover, setHover] = useState<number | null>(null);
  const plotRef = useRef<HTMLDivElement>(null);

  const colorOf = (id: string) => SERIES[providerOrder.indexOf(id)] ?? OVERFLOW;
  const recorded = result?.samples.map((s) => s.ele) ?? [];
  const hasRecorded = recorded.some((e) => e != null);
  const effectiveMode: Mode = hasRecorded ? mode : "heights";
  const ok = result?.providers.filter((p) => p.heights) ?? [];

  const series: Series[] =
    effectiveMode === "heights"
      ? [
          ...(hasRecorded ? [{ id: "recorded", label: "Recorded", color: RECORDED, values: recorded, dashed: true }] : []),
          ...ok.map((p) => ({ id: p.id, label: p.label, color: colorOf(p.id), values: p.heights! })),
        ]
      : ok.map((p) => ({
          id: p.id,
          label: p.label,
          color: colorOf(p.id),
          values: p.heights!.map((h, k) => (h != null && recorded[k] != null ? h - recorded[k]! : null)),
        }));

  const all = series.flatMap((s) => s.values).filter((v): v is number => v != null);
  const plot =
    result && all.length
      ? (() => {
          let lo = Math.min(...all, ...(effectiveMode === "difference" ? [0] : []));
          let hi = Math.max(...all, ...(effectiveMode === "difference" ? [0] : []));
          const pad = Math.max(1, (hi - lo) * 0.05);
          lo -= pad;
          hi += pad;
          const total = result.samples[result.samples.length - 1].d || 1;
          const xOf = (d: number) => PAD_L + (d / total) * (W - PAD_L - PAD_R);
          const yOf = (v: number) => PAD_T + (1 - (v - lo) / (hi - lo)) * (H - PAD_T - PAD_B);
          return { lo, hi, total, xOf, yOf, xs: result.samples.map((s) => xOf(s.d)) };
        })()
      : null;

  const onMove = (e: React.MouseEvent) => {
    if (!plot || !result || !plotRef.current) return;
    const rect = plotRef.current.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * W;
    let best = 0;
    plot.xs.forEach((sx, k) => {
      if (Math.abs(sx - x) < Math.abs(plot.xs[best] - x)) best = k;
    });
    setHover(best);
  };

  return (
    <>
      <div className="fixed inset-0 z-[1900] bg-black/40" onClick={onClose} />
      <div
        role="dialog"
        aria-label="Elevation source comparison"
        className="fixed z-[2000] left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[min(64rem,calc(100vw-2rem))] max-h-[calc(100vh-2rem)] overflow-y-auto bg-surface rounded-lg shadow-card border border-line p-4 flex flex-col gap-3 text-sm"
      >
        <div className="flex items-center justify-between gap-2">
          <h2 className="font-semibold">Elevation sources compared</h2>
          <button className="btn" onClick={onClose}>
            Close
          </button>
        </div>

        {pending && <p className="text-ink-muted">Looking up heights... rate-limited sources take about a second per 100 points.</p>}
        {error && <p className="text-red-600">{error}</p>}

        {result && (
          <>
            <p className="hint">
              {result.samples.length} evenly spaced points from {result.point_count.toLocaleString()} on this day (
              {(result.distance_m / 1000).toFixed(1)} km).{" "}
              {hasRecorded
                ? "Differences are source minus recorded. Climbing totals use the same sampled points for every series, so they read lower than the day's full figure."
                : "This day has no recorded heights, so there's nothing to score against - only the sources' own profiles."}
            </p>

            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div className="flex items-center gap-3 flex-wrap text-xs text-ink">
                {series.map((s) => (
                  <span key={s.id} className="inline-flex items-center gap-1.5">
                    <svg width="18" height="8" aria-hidden>
                      <line x1="0" y1="4" x2="18" y2="4" stroke={s.color} strokeWidth="2" strokeDasharray={s.dashed ? "4 3" : undefined} />
                    </svg>
                    {s.label}
                  </span>
                ))}
              </div>
              {hasRecorded && (
                <div className="inline-flex rounded-md border border-line overflow-hidden text-xs">
                  {(["heights", "difference"] as Mode[]).map((m) => (
                    <button
                      key={m}
                      className={`px-2 py-1 ${effectiveMode === m ? "bg-page font-medium" : ""}`}
                      onClick={() => setMode(m)}
                    >
                      {m === "heights" ? "Heights" : "Difference from recorded"}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {plot ? (
              <div ref={plotRef} className="relative" onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
                <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto block">
                  {ticks(plot.lo, plot.hi).map((t) => (
                    <g key={t}>
                      <line
                        x1={PAD_L}
                        x2={W - PAD_R}
                        y1={plot.yOf(t)}
                        y2={plot.yOf(t)}
                        stroke={t === 0 && effectiveMode === "difference" ? "#9ca3af" : "#e5e7eb"}
                        strokeWidth={1}
                      />
                      <text x={PAD_L - 6} y={plot.yOf(t) + 4} fontSize={11} textAnchor="end" fill="#6b7280">
                        {t}
                      </text>
                    </g>
                  ))}
                  {ticks(0, plot.total / 1000, 8).map((km) => (
                    <text key={km} x={plot.xOf(km * 1000)} y={H - 8} fontSize={11} textAnchor="middle" fill="#6b7280">
                      {km} km
                    </text>
                  ))}
                  <text x={4} y={PAD_T + 4} fontSize={11} fill="#6b7280">
                    m
                  </text>

                  {series.map((s) => (
                    <path
                      key={s.id}
                      d={pathOf(plot.xs, s.values.map((v) => (v == null ? null : plot.yOf(v))))}
                      fill="none"
                      stroke={s.color}
                      strokeWidth={2}
                      strokeDasharray={s.dashed ? "6 4" : undefined}
                      strokeLinejoin="round"
                    />
                  ))}

                  {hover != null && (
                    <g>
                      <line x1={plot.xs[hover]} x2={plot.xs[hover]} y1={PAD_T} y2={H - PAD_B} stroke="#9ca3af" strokeWidth={1} />
                      {series.map((s) =>
                        s.values[hover] != null ? (
                          <circle
                            key={s.id}
                            cx={plot.xs[hover]}
                            cy={plot.yOf(s.values[hover]!)}
                            r={4}
                            fill={s.color}
                            stroke="#fff"
                            strokeWidth={2}
                          />
                        ) : null
                      )}
                    </g>
                  )}
                </svg>

                {hover != null && (
                  <div
                    className="absolute top-2 pointer-events-none bg-surface border border-line rounded-md shadow-card px-2 py-1.5 text-xs"
                    style={
                      plot.xs[hover] / W > 0.6
                        ? { right: `${(1 - plot.xs[hover] / W) * 100 + 1}%` }
                        : { left: `${(plot.xs[hover] / W) * 100 + 1}%` }
                    }
                  >
                    <div className="text-ink-muted mb-0.5">
                      {(result.samples[hover].d / 1000).toFixed(1)} km · point {result.samples[hover].index}
                    </div>
                    {series.map((s) => (
                      <div key={s.id} className="flex items-center justify-between gap-3">
                        <span className="inline-flex items-center gap-1.5 text-ink">
                          <span className="inline-block w-2 h-2 rounded-full" style={{ background: s.color }} />
                          {s.label}
                        </span>
                        <span className="tabular-nums text-ink">
                          {fmt(s.values[hover], effectiveMode === "difference")} m
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <p className="text-ink-muted">No source returned any heights.</p>
            )}

            <table className="w-full text-xs tabular-nums">
              <thead className="text-ink-muted text-left">
                <tr className="border-b border-line">
                  <th className="py-1 font-medium">Source</th>
                  <th className="py-1 font-medium text-right" title="Average of source minus recorded: positive reads high">Bias (m)</th>
                  <th className="py-1 font-medium text-right" title="Mean absolute error">MAE (m)</th>
                  <th className="py-1 font-medium text-right" title="Root mean square error - punishes big misses">RMSE (m)</th>
                  <th className="py-1 font-medium text-right" title="Largest single difference">Max (m)</th>
                  <th className="py-1 font-medium text-right">Ascent</th>
                  <th className="py-1 font-medium text-right">Descent</th>
                  <th className="py-1 font-medium text-right">Time</th>
                </tr>
              </thead>
              <tbody>
                {result.recorded && (
                  <tr className="border-b border-line">
                    <td className="py-1 text-ink">Recorded</td>
                    <td colSpan={4} className="py-1 text-right text-ink-faint">reference</td>
                    <td className="py-1 text-right">{result.recorded.ascent_m} m</td>
                    <td className="py-1 text-right">{result.recorded.descent_m} m</td>
                    <td />
                  </tr>
                )}
                {result.providers.map((p) => (
                  <tr key={p.id} className="border-b border-line" title={p.description}>
                    <td className="py-1 text-ink">
                      <span className="inline-flex items-center gap-1.5">
                        <span className="inline-block w-2 h-2 rounded-full" style={{ background: colorOf(p.id) }} />
                        {p.label}
                      </span>
                    </td>
                    {p.error ? (
                      <td colSpan={7} className="py-1 text-red-600">
                        {p.error}
                      </td>
                    ) : (
                      <>
                        <td className="py-1 text-right">{fmt(p.stats?.bias_m, true)}</td>
                        <td className="py-1 text-right">{fmt(p.stats?.mae_m)}</td>
                        <td className="py-1 text-right">{fmt(p.stats?.rmse_m)}</td>
                        <td className="py-1 text-right">{fmt(p.stats?.max_abs_m)}</td>
                        <td className="py-1 text-right">{p.profile ? `${p.profile.ascent_m} m` : "-"}</td>
                        <td className="py-1 text-right">{p.profile ? `${p.profile.descent_m} m` : "-"}</td>
                        <td className="py-1 text-right text-ink-muted">{p.seconds != null ? `${p.seconds}s` : "-"}</td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>
    </>
  );
}
