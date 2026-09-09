import { useEffect, useState } from "react";
import type { DayDetail } from "../api/types";
import { useRotate, useSetDayEdge, useTrim } from "../api/hooks";

export interface ContextTarget {
  /** Set when the click landed on another day shown behind this one. */
  otherDayId: number | null;
  otherDayName?: string;
  /** Where the clicked day sits relative to the one being edited. */
  otherDayRelation?: "previous" | "next" | "distant";
  index: number;
  x: number;
  y: number;
  /** Whether the day being edited has a neighbour on each side. Its edge is a
   *  shared boundary where it does, and just the end of the line where it doesn't. */
  hasPrevious: boolean;
  hasNext: boolean;
}

interface Props {
  projectId: number;
  day: DayDetail;
  target: ContextTarget;
  onClose: () => void;
}

const MENU_WIDTH = 260;
const MENU_HEIGHT_ESTIMATE = 190;

export default function PointContextMenu({ projectId, day, target, onClose }: Props) {
  const rotate = useRotate(projectId);
  const trim = useTrim(projectId);
  const setEdge = useSetDayEdge(projectId);
  const [pos] = useState(() => ({
    left: Math.min(target.x, window.innerWidth - MENU_WIDTH - 8),
    top: Math.min(target.y, window.innerHeight - MENU_HEIGHT_ESTIMATE - 8),
  }));

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const act = (fn: () => void) => () => {
    fn();
    onClose();
  };

  const onOtherDay = target.otherDayId != null;
  // The chosen point belongs to whichever day was actually clicked.
  const pointDayId = target.otherDayId ?? day.id;

  // Where a neighbour exists, this edge is the boundary shared with it, so the
  // stretch between old and new position moves across rather than being lost.
  const setStart = act(() =>
    target.hasPrevious
      ? setEdge.mutate({ dayId: day.id, edge: "start", pointDayId, pointIndex: target.index })
      : trim.mutate({ dayId: day.id, start_index: target.index, end_index: day.points.length - 1 })
  );

  const setEnd = act(() =>
    target.hasNext
      ? setEdge.mutate({ dayId: day.id, edge: "end", pointDayId, pointIndex: target.index })
      : trim.mutate({ dayId: day.id, start_index: 0, end_index: target.index })
  );

  const item =
    "w-full text-left px-3 py-1.5 hover:bg-page disabled:opacity-40 disabled:cursor-not-allowed";
  const note = "block text-[11px] text-ink-muted";

  return (
    <>
      <div
        className="fixed inset-0 z-[1900]"
        onClick={onClose}
        onContextMenu={(e) => {
          e.preventDefault();
          onClose();
        }}
      />
      <div
        className="fixed z-[2000] bg-surface border border-line rounded-lg shadow-lg text-sm py-1"
        style={{ left: pos.left, top: pos.top, width: MENU_WIDTH }}
      >
        <div className="px-3 py-1 text-xs text-ink-faint border-b border-line">
          {onOtherDay ? `On "${target.otherDayName ?? "another day"}"` : "This day"} - point{" "}
          {target.index}
        </div>

        {day.is_locked ? (
          <div className="px-3 py-2 text-xs text-amber-600">
            Day is locked - unlock it to change the route.
          </div>
        ) : onOtherDay ? (
          <>
            {target.otherDayRelation === "previous" && (
              <button className={item} onClick={setStart}>
                Start this day here
                <span className={note}>the previous day ends here instead</span>
              </button>
            )}
            {target.otherDayRelation === "next" && (
              <button className={item} onClick={setEnd}>
                End this day here
                <span className={note}>the next day starts here instead</span>
              </button>
            )}
            {target.otherDayRelation === "distant" && (
              <div className="px-3 py-2 text-[11px] text-ink-muted">
                Only the days immediately before and after can be adjusted from here - there's a
                whole day in between.
              </div>
            )}
          </>
        ) : day.is_circular ? (
          <button
            className={item}
            onClick={act(() => rotate.mutate({ dayId: day.id, index: target.index }))}
          >
            Set as start/end (rotate loop here)
          </button>
        ) : (
          <>
            <button className={item} disabled={target.index === 0} onClick={setStart}>
              Set as start
              <span className={note}>
                {target.hasPrevious ? "the previous day takes the rest" : "trims the route"}
              </span>
            </button>
            <button
              className={item}
              disabled={target.index === day.points.length - 1}
              onClick={setEnd}
            >
              Set as end
              <span className={note}>
                {target.hasNext ? "the next day takes the rest" : "trims the route"}
              </span>
            </button>
          </>
        )}

        {(setEdge.isError || trim.isError) && (
          <div className="px-3 py-1 text-[11px] text-red-600">
            {((setEdge.error ?? trim.error) as Error)?.message}
          </div>
        )}
      </div>
    </>
  );
}
