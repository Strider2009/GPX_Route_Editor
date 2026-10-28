import { useMemo, useRef, useState } from "react";
import type { DayGeometry, PotholeMatch, RoadworkMatch } from "../api/types";
import { haversine } from "../lib/geo";
import { dayColor } from "../lib/dayColors";
import { useUIStore } from "../state/uiStore";
import { RELEVANCE_COLORS } from "./RoadworksPanel";
import { POTHOLE_COLOR } from "./PotholePanel";

interface Props {
  /** Every day in the trip, in trip order. The profile spans them all. */
  days: DayGeometry[];
  selectedDayId: number | null;
  dayColors: Map<number, string>;
  /** Matches for the selected day; their indices are into that day's points. */
  roadworks: RoadworkMatch[];
  potholes: PotholeMatch[];
}

const HEIGHT = 130;
const PAD_L = 34;
const PAD_B = 16;
const PAD_T = 6;

/** One plotted point: `i` is its index in its day's full route, `d` the distance along the whole trip. */
interface Sample {
  i: number;
  d: number;
  ele: number;
}

interface DaySpan {
  dayId: number;
  number: number;
  color: string;
  start: number;
  end: number;
  samples: Sample[];
}

/** Find the sample pair either side of `value`, and how far between them it sits. */
function bracket(samples: Sample[], key: "i" | "d", value: number): [Sample, Sample, number] {
  let lo = 0;
  let hi = samples.length - 1;
  if (value <= samples[0][key]) return [samples[0], samples[0], 0];
  if (value >= samples[hi][key]) return [samples[hi], samples[hi], 0];
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (samples[mid][key] <= value) lo = mid;
    else hi = mid;
  }
  const a = samples[lo];
  const b = samples[hi];
  const t = b[key] === a[key] ? 0 : (value - a[key]) / (b[key] - a[key]);
  return [a, b, t];
}

export default function ElevationProfile({ days, selectedDayId, dayColors, roadworks, potholes }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const selectedPointIndex = useUIStore((s) => s.selectedPointIndex);
  const setSelectedPoint = useUIStore((s) => s.setSelectedPoint);
  const setSelectedDay = useUIStore((s) => s.setSelectedDay);
  const hoveredPointIndex = useUIStore((s) => s.hoveredPointIndex);
  const setHoveredPoint = useUIStore((s) => s.setHoveredPoint);
  // Trip distance under the cursor. Kept here as well as in the store because the
  // store's hover is an index into the selected day and can't describe the others.
  const [cursorD, setCursorD] = useState<number | null>(null);

  const model = useMemo(() => {
    // Gaps are carried forward; a route that opens without elevation borrows its first reading.
    const firstEle = days.flatMap((g) => g.points).find((p) => p[3] != null)?.[3];
    if (firstEle == null) return null;

    let lastEle = firstEle;
    let offset = 0;
    const spans: DaySpan[] = [];
    days.forEach((g, n) => {
      if (g.points.length === 0) return;
      const samples: Sample[] = [];
      let d = offset;
      g.points.forEach((p, k) => {
        if (k > 0) {
          const q = g.points[k - 1];
          d += haversine({ lat: q[0], lon: q[1] }, { lat: p[0], lon: p[1] });
        }
        lastEle = p[3] ?? lastEle;
        samples.push({ i: p[2], d, ele: lastEle });
      });
      spans.push({
        dayId: g.day_id,
        number: n + 1,
        color: dayColors.get(g.day_id) ?? dayColor(n),
        start: offset,
        end: d,
        samples,
      });
      // Consecutive days share their boundary point, so the next one picks up here.
      offset = d;
    });
    if (spans.length === 0) return null;

    const eles = spans.flatMap((s) => s.samples.map((x) => x.ele));
    const minEle = Math.min(...eles);
    const maxEle = Math.max(...eles);
    return { spans, total: offset || 1, minEle, maxEle, span: Math.max(1, maxEle - minEle) };
  }, [days, dayColors]);

  if (!model) {
    return <div className="text-xs text-ink-muted px-2 py-3">This route has no elevation data. Use Elevation data in the sidebar to fill it.</div>;
  }

  const { spans, total, minEle, maxEle, span } = model;
  const multiDay = spans.length > 1;
  const current = spans.find((s) => s.dayId === selectedDayId) ?? null;

  // Viewbox is 1000 wide; the SVG scales to whatever width it's given.
  const W = 1000;
  const xOf = (d: number) => PAD_L + (d / total) * (W - PAD_L - 4);
  const yOf = (e: number) => PAD_T + (1 - (e - minEle) / span) * (HEIGHT - PAD_T - PAD_B);
  const baseY = HEIGHT - PAD_B;

  /** Trip distance of a point on the selected day. */
  const distOf = (index: number): number | null => {
    if (!current) return null;
    const [a, b, t] = bracket(current.samples, "i", index);
    return a.d + (b.d - a.d) * t;
  };

  /** The day and point at a trip distance. The selected day wins at a shared boundary. */
  const locate = (d: number) => {
    const s =
      (current && d >= current.start && d <= current.end ? current : null) ??
      spans.find((x) => d <= x.end) ??
      spans[spans.length - 1];
    const [a, b, t] = bracket(s.samples, "d", d);
    return {
      span: s,
      index: Math.round(a.i + (b.i - a.i) * t),
      ele: a.ele + (b.ele - a.ele) * t,
      dayD: d - s.start,
    };
  };

  const distAt = (clientX: number): number | null => {
    const svg = svgRef.current;
    if (!svg) return null;
    const rect = svg.getBoundingClientRect();
    const frac = (clientX - rect.left) / rect.width;
    return Math.max(0, Math.min(total, ((frac * W - PAD_L) / (W - PAD_L - 4)) * total));
  };

  const selectedD = selectedPointIndex != null ? distOf(selectedPointIndex) : null;
  const hoveredD = cursorD ?? (hoveredPointIndex != null ? distOf(hoveredPointIndex) : null);
  // What the readout describes: the cursor takes priority while it's over the plot.
  const readoutD = hoveredD ?? selectedD;
  const readout = readoutD != null ? locate(readoutD) : null;

  return (
    <div className="border-t bg-white">
      <div className="flex items-center justify-between px-2 pt-1 text-[11px] text-ink-muted">
        <span>Elevation</span>
        <span>
          {(total / 1000).toFixed(1)} km · {Math.round(minEle)}-{Math.round(maxEle)} m
          {readout && (
            <span className={`ml-2 ${hoveredD != null ? "text-ink-muted" : "text-ink"}`}>
              @ {multiDay && `Day ${readout.span.number}, `}
              {(readout.dayD / 1000).toFixed(1)} km, {Math.round(readout.ele)} m
              {hoveredD != null && (
                <span className="text-ink-faint">
                  {" "}
                  (click to {readout.span.dayId === selectedDayId ? "centre" : "open day"})
                </span>
              )}
            </span>
          )}
        </span>
      </div>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${HEIGHT}`}
        preserveAspectRatio="none"
        className="w-full cursor-crosshair"
        style={{ height: HEIGHT }}
        onClick={(e) => {
          const d = distAt(e.clientX);
          if (d == null) return;
          const hit = locate(d);
          if (hit.span.dayId !== selectedDayId) setSelectedDay(hit.span.dayId);
          setSelectedPoint(hit.index);
        }}
        onMouseMove={(e) => {
          const d = distAt(e.clientX);
          setCursorD(d);
          const hit = d != null ? locate(d) : null;
          setHoveredPoint(hit && hit.span.dayId === selectedDayId ? hit.index : null);
        }}
        onMouseLeave={() => {
          setCursorD(null);
          setHoveredPoint(null);
        }}
      >
        {[minEle, (minEle + maxEle) / 2, maxEle].map((e, i) => (
          <g key={i}>
            <line x1={PAD_L} y1={yOf(e)} x2={W - 4} y2={yOf(e)} stroke="#e5e7eb" strokeWidth={0.5} />
            <text x={2} y={yOf(e) + 3} fontSize={9} fill="#9ca3af">
              {Math.round(e)}m
            </text>
          </g>
        ))}

        {spans.map((s) => {
          const isCurrent = !multiDay || s.dayId === selectedDayId;
          const line = s.samples.map((x) => `${xOf(x.d).toFixed(1)},${yOf(x.ele).toFixed(1)}`).join(" ");
          return (
            <g key={s.dayId}>
              <polygon
                points={`${xOf(s.start)},${baseY} ${line} ${xOf(s.end)},${baseY}`}
                fill={s.color}
                fillOpacity={isCurrent ? 0.3 : 0.12}
              />
              <polyline
                points={line}
                fill="none"
                stroke={s.color}
                strokeWidth={isCurrent ? 2 : 1.25}
                strokeOpacity={isCurrent ? 1 : 0.7}
              />
            </g>
          );
        })}

        {multiDay &&
          spans.map((s) => (
            <g key={`label-${s.dayId}`}>
              {s.number > 1 && (
                <line x1={xOf(s.start)} y1={PAD_T} x2={xOf(s.start)} y2={baseY} stroke="#d1d5db" strokeWidth={1} />
              )}
              {/* Skip the label where a short day leaves no room for it. */}
              {xOf(s.end) - xOf(s.start) > 40 && (
                <text
                  x={xOf(s.start) + 4}
                  y={PAD_T + 9}
                  fontSize={9}
                  fontWeight={s.dayId === selectedDayId ? 700 : 400}
                  fill={s.color}
                >
                  Day {s.number}
                </text>
              )}
            </g>
          ))}

        {roadworks.map((w) => {
          const d = distOf(w.nearest_point_index);
          return d != null ? (
            <line
              key={`rw-${w.external_id}`}
              x1={xOf(d)}
              y1={PAD_T}
              x2={xOf(d)}
              y2={baseY}
              stroke={RELEVANCE_COLORS[w.cycling_relevance]}
              strokeWidth={1.5}
              opacity={0.75}
            />
          ) : null;
        })}
        {potholes.map((p) => {
          const d = distOf(p.nearest_point_index);
          return d != null ? (
            <circle key={`ph-${p.report_id}`} cx={xOf(d)} cy={baseY - 3} r={2.5} fill={POTHOLE_COLOR} />
          ) : null;
        })}

        {hoveredD != null && hoveredD !== selectedD && (
          <line
            x1={xOf(hoveredD)}
            y1={PAD_T}
            x2={xOf(hoveredD)}
            y2={baseY}
            stroke="#9ca3af"
            strokeWidth={1}
            strokeDasharray="3 3"
          />
        )}
        {selectedD != null && (
          <line x1={xOf(selectedD)} y1={PAD_T} x2={xOf(selectedD)} y2={baseY} stroke="#facc15" strokeWidth={2} />
        )}
        <line x1={PAD_L} y1={baseY} x2={W - 4} y2={baseY} stroke="#d1d5db" />
      </svg>
    </div>
  );
}
