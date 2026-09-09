import { useMemo, useRef } from "react";
import type { Point, PotholeMatch, RoadworkMatch } from "../api/types";
import { cumulativeDistances } from "../lib/geo";
import { useUIStore } from "../state/uiStore";
import { RELEVANCE_COLORS } from "./RoadworksPanel";
import { POTHOLE_COLOR } from "./PotholePanel";

interface Props {
  points: Point[];
  roadworks: RoadworkMatch[];
  potholes: PotholeMatch[];
}

const HEIGHT = 130;
const PAD_L = 34;
const PAD_B = 16;
const PAD_T = 6;
// Drawing every one of several thousand points makes a needlessly heavy path.
const MAX_SAMPLES = 600;

export default function ElevationProfile({ points, roadworks, potholes }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const selectedPointIndex = useUIStore((s) => s.selectedPointIndex);
  const setSelectedPoint = useUIStore((s) => s.setSelectedPoint);
  const hoveredPointIndex = useUIStore((s) => s.hoveredPointIndex);
  const setHoveredPoint = useUIStore((s) => s.setHoveredPoint);

  const model = useMemo(() => {
    if (points.length < 2) return null;
    const dists = cumulativeDistances(points);
    const total = dists[dists.length - 1] || 1;

    const step = Math.max(1, Math.floor(points.length / MAX_SAMPLES));
    const samples: { i: number; d: number; ele: number }[] = [];
    let lastEle = 0;
    for (let i = 0; i < points.length; i += step) {
      const ele = points[i].ele ?? lastEle;
      lastEle = ele;
      samples.push({ i, d: dists[i], ele });
    }
    const last = points.length - 1;
    samples.push({ i: last, d: dists[last], ele: points[last].ele ?? lastEle });

    const eles = samples.map((s) => s.ele);
    const minEle = Math.min(...eles);
    const maxEle = Math.max(...eles);
    const span = Math.max(1, maxEle - minEle);
    return { dists, total, samples, minEle, maxEle, span };
  }, [points]);

  if (!model) return <div className="text-xs text-ink-muted p-2">No elevation data.</div>;

  const { dists, total, samples, minEle, maxEle, span } = model;

  // Viewbox is 1000 wide; the SVG scales to whatever width it's given.
  const W = 1000;
  const xOf = (d: number) => PAD_L + (d / total) * (W - PAD_L - 4);
  const yOf = (e: number) => PAD_T + (1 - (e - minEle) / span) * (HEIGHT - PAD_T - PAD_B);

  const line = samples.map((s) => `${xOf(s.d).toFixed(1)},${yOf(s.ele).toFixed(1)}`).join(" ");
  const area = `${xOf(0)},${HEIGHT - PAD_B} ${line} ${xOf(total)},${HEIGHT - PAD_B}`;

  /** Index of the route point under a given screen x, or null if off the plot. */
  const indexAt = (clientX: number): number | null => {
    const svg = svgRef.current;
    if (!svg) return null;
    const rect = svg.getBoundingClientRect();
    const frac = (clientX - rect.left) / rect.width;
    const targetD = ((frac * W - PAD_L) / (W - PAD_L - 4)) * total;
    // Nearest point by distance along the route.
    let lo = 0;
    let hi = dists.length - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (dists[mid] < targetD) lo = mid + 1;
      else hi = mid;
    }
    return Math.max(0, Math.min(points.length - 1, lo));
  };

  const inRange = (i: number | null) => (i != null && i < dists.length ? i : null);
  const selected = inRange(selectedPointIndex);
  const hovered = inRange(hoveredPointIndex);
  // What the readout describes: the cursor takes priority while it's over the plot.
  const readout = hovered ?? selected;

  return (
    <div className="border-t bg-white">
      <div className="flex items-center justify-between px-2 pt-1 text-[11px] text-ink-muted">
        <span>Elevation</span>
        <span>
          {(total / 1000).toFixed(1)} km · {Math.round(minEle)}-{Math.round(maxEle)} m
          {readout != null && points[readout] && (
            <span className={`ml-2 ${hovered != null ? "text-ink-muted" : "text-ink"}`}>
              @ {(dists[readout] / 1000).toFixed(1)} km,{" "}
              {points[readout].ele != null ? `${Math.round(points[readout].ele!)} m` : "no ele"}
              {hovered != null && <span className="text-ink-faint"> (click to centre)</span>}
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
          const i = indexAt(e.clientX);
          if (i != null) setSelectedPoint(i);
        }}
        onMouseMove={(e) => setHoveredPoint(indexAt(e.clientX))}
        onMouseLeave={() => setHoveredPoint(null)}
      >
        <polygon points={area} fill="#dbeafe" />
        <polyline points={line} fill="none" stroke="#2563eb" strokeWidth={1.5} />

        {[minEle, (minEle + maxEle) / 2, maxEle].map((e, i) => (
          <g key={i}>
            <line x1={PAD_L} y1={yOf(e)} x2={W - 4} y2={yOf(e)} stroke="#e5e7eb" strokeWidth={0.5} />
            <text x={2} y={yOf(e) + 3} fontSize={9} fill="#9ca3af">
              {Math.round(e)}m
            </text>
          </g>
        ))}

        {roadworks.map((w) =>
          w.nearest_point_index < dists.length ? (
            <line
              key={`rw-${w.external_id}`}
              x1={xOf(dists[w.nearest_point_index])}
              y1={PAD_T}
              x2={xOf(dists[w.nearest_point_index])}
              y2={HEIGHT - PAD_B}
              stroke={RELEVANCE_COLORS[w.cycling_relevance]}
              strokeWidth={1.5}
              opacity={0.75}
            />
          ) : null
        )}
        {potholes.map((p) =>
          p.nearest_point_index < dists.length ? (
            <circle
              key={`ph-${p.report_id}`}
              cx={xOf(dists[p.nearest_point_index])}
              cy={HEIGHT - PAD_B - 3}
              r={2.5}
              fill={POTHOLE_COLOR}
            />
          ) : null
        )}

        {hovered != null && hovered !== selected && (
          <line
            x1={xOf(dists[hovered])}
            y1={PAD_T}
            x2={xOf(dists[hovered])}
            y2={HEIGHT - PAD_B}
            stroke="#9ca3af"
            strokeWidth={1}
            strokeDasharray="3 3"
          />
        )}
        {selected != null && (
          <line
            x1={xOf(dists[selected])}
            y1={PAD_T}
            x2={xOf(dists[selected])}
            y2={HEIGHT - PAD_B}
            stroke="#facc15"
            strokeWidth={2}
          />
        )}
        <line x1={PAD_L} y1={HEIGHT - PAD_B} x2={W - 4} y2={HEIGHT - PAD_B} stroke="#d1d5db" />
      </svg>
    </div>
  );
}
