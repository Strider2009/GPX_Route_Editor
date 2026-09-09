import { useEffect, useMemo, useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { Point } from "../api/types";
import { useUIStore } from "../state/uiStore";
import { cumulativeDistances } from "../lib/geo";

interface Props {
  points: Point[];
  dayName: string;
  isCircular: boolean;
  onContextMenu: (pointIndex: number, screenX: number, screenY: number) => void;
}

const ROW_CLASS = "grid grid-cols-[3rem_1fr_1fr_4rem_5rem] gap-1 px-2 text-xs items-center";

export default function PointList({ points, dayName, isCircular, onContextMenu }: Props) {
  const parentRef = useRef<HTMLDivElement>(null);
  const selectedPointIndex = useUIStore((s) => s.selectedPointIndex);
  const setSelectedPoint = useUIStore((s) => s.setSelectedPoint);
  const rangeStart = useUIStore((s) => s.rangeStart);

  const distances = useMemo(() => cumulativeDistances(points), [points]);

  const rowVirtualizer = useVirtualizer({
    count: points.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 26,
    overscan: 15,
  });

  const lastIndex = points.length - 1;

  useEffect(() => {
    if (selectedPointIndex != null) {
      rowVirtualizer.scrollToIndex(selectedPointIndex, { align: "auto" });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedPointIndex]);

  return (
    <div className="flex flex-col h-full">
      <div className="px-2 py-1.5 border-b border-line bg-page text-sm font-semibold truncate" title={dayName}>
        {dayName}
      </div>
      <div className={`${ROW_CLASS} py-1 font-semibold text-ink-muted border-b border-line bg-page`}>
        <span>#</span>
        <span>Lat</span>
        <span>Lon</span>
        <span>Ele</span>
        <span>Dist</span>
      </div>
      <div ref={parentRef} className="flex-1 overflow-y-auto relative">
        <div style={{ height: rowVirtualizer.getTotalSize(), position: "relative" }}>
          {rowVirtualizer.getVirtualItems().map((vi) => {
            const p = points[vi.index];
            const selected = vi.index === selectedPointIndex;
            const isRangeStart = vi.index === rangeStart;
            const isStart = vi.index === 0;
            const isLoopClosure = isCircular && vi.index === lastIndex && lastIndex !== 0;
            const isEnd = !isCircular && vi.index === lastIndex;
            const rowTitle = isStart && isEnd ? "Start / end" : isStart ? "Start" : isEnd ? "End" : isLoopClosure ? "Loop closes here (same point as start)" : undefined;
            return (
              <div
                key={vi.index}
                onClick={() => setSelectedPoint(vi.index)}
                onContextMenu={(e) => {
                  e.preventDefault();
                  setSelectedPoint(vi.index);
                  onContextMenu(vi.index, e.clientX, e.clientY);
                }}
                title={rowTitle}
                className={`${ROW_CLASS} cursor-pointer absolute left-0 right-0 border-l-4 ${
                  isStart ? "border-l-green-500" : isEnd ? "border-l-red-500" : isLoopClosure ? "border-l-green-300" : "border-l-transparent"
                } ${selected ? "bg-brand-tint" : isRangeStart ? "bg-amber-100" : "hover:bg-page"}`}
                style={{ height: vi.size, transform: `translateY(${vi.start}px)` }}
              >
                <span className="flex items-center gap-1">
                  {vi.index}
                  {isStart && (
                    <span className="text-[10px] font-bold text-green-600" title="Start">
                      S
                    </span>
                  )}
                  {isEnd && (
                    <span className="text-[10px] font-bold text-red-600" title="End">
                      E
                    </span>
                  )}
                  {isLoopClosure && (
                    <span className="text-[10px] font-bold text-green-500" title="Loop closes here (same point as start)">
                      &#8635;
                    </span>
                  )}
                </span>
                <span>{p.lat.toFixed(5)}</span>
                <span>{p.lon.toFixed(5)}</span>
                <span>{p.ele != null ? Math.round(p.ele) : "-"}</span>
                <span>{(distances[vi.index] / 1000).toFixed(2)} km</span>
              </div>
            );
          })}
        </div>
      </div>
      {points.length === 0 && <div className="p-4 text-sm text-ink-muted">No points.</div>}
    </div>
  );
}
