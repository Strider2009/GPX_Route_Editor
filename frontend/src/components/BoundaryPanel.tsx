import { useEffect, useState } from "react";
import { useBoundaries, useMoveBoundary, useShiftBoundaries } from "../api/hooks";

interface Props {
  projectId: number;
}

function km(m: number): string {
  return `${(m / 1000).toFixed(1)} km`;
}

export default function BoundaryPanel({ projectId }: Props) {
  const { data, isLoading } = useBoundaries(projectId);
  const moveBoundary = useMoveBoundary(projectId);
  const shiftAll = useShiftBoundaries(projectId);

  // Slider positions are transient: they snap back to centre after each move,
  // because the boundary itself has then moved to where you put it.
  const [drafts, setDrafts] = useState<Record<number, number>>({});
  const [shift, setShift] = useState(0);

  useEffect(() => {
    setDrafts({});
    setShift(0);
  }, [data]);

  if (isLoading || !data) return null;
  if (data.boundaries.length === 0) {
    return (
      <div className="panel">
        <h3 className="panel-title">Day boundaries</h3>
        <p className="hint">
          Only one day, so there's nothing to move. Split it first.
        </p>
      </div>
    );
  }

  const busy = moveBoundary.isPending || shiftAll.isPending;

  return (
    <div className="panel">
      <h3 className="panel-title">Day boundaries</h3>
      <p className="hint">
        Each boundary is one point shared by two days, so moving it shortens one and lengthens the
        other. Locking either neighbour, or pinning the end that meets it, holds it in place.
      </p>

      <div className="text-xs text-ink-muted">
        {data.movable_count} of {data.boundaries.length} can move
      </div>

      {data.movable_count > 1 && (
        <div className="rounded-md p-2 flex flex-col gap-1 bg-brand-tint border border-brand/20">
          <div className="text-xs font-semibold text-ink">Shift them all together</div>
          <input
            type="range"
            min={-20000}
            max={20000}
            step={250}
            value={shift}
            disabled={busy}
            onChange={(e) => setShift(Number(e.target.value))}
            className="w-full"
          />
          <div className="flex items-center justify-between text-xs">
            <span className={shift === 0 ? "text-ink-faint" : "text-ink"}>
              {shift > 0 ? "+" : ""}
              {(shift / 1000).toFixed(2)} km
            </span>
            <div className="flex gap-1">
              <button className="btn text-xs" disabled={busy || shift === 0} onClick={() => setShift(0)}>
                Reset
              </button>
              <button
                className="btn-primary text-xs"
                disabled={busy || shift === 0}
                onClick={() => shiftAll.mutate(shift)}
              >
                {shiftAll.isPending ? "..." : "Apply"}
              </button>
            </div>
          </div>
          {shiftAll.data && (
            <div className="hint">
              moved {shiftAll.data.boundaries_moved}
              {shiftAll.data.boundaries_skipped.length > 0 &&
                `, ${shiftAll.data.boundaries_skipped.length} held by locks`}
            </div>
          )}
        </div>
      )}

      <ul className="flex flex-col gap-2">
        {data.boundaries.map((b) => {
          const draft = drafts[b.index] ?? 0;
          return (
            <li key={b.index} className="border border-line rounded-md p-2 flex flex-col gap-1">
              <div className="flex items-center justify-between gap-2 text-xs">
                <span className="truncate">
                  <span className="text-ink-muted">{b.wraps ? "loop join after" : "end of"}</span>{" "}
                  {b.day_a_name.slice(-14)}
                </span>
                <span className="text-ink-faint shrink-0">
                  {km(b.day_a_distance_m)} | {km(b.day_b_distance_m)}
                </span>
              </div>

              {b.movable ? (
                <>
                  <input
                    type="range"
                    min={-Math.round(b.max_back_m)}
                    max={Math.round(b.max_forward_m)}
                    step={100}
                    value={draft}
                    disabled={busy}
                    onChange={(e) =>
                      setDrafts((d) => ({ ...d, [b.index]: Number(e.target.value) }))
                    }
                    className="w-full"
                  />
                  <div className="flex items-center justify-between text-xs">
                    <span className={draft === 0 ? "text-ink-faint" : "text-ink"}>
                      {draft > 0 ? "+" : ""}
                      {(draft / 1000).toFixed(2)} km
                    </span>
                    <button
                      className="btn-primary text-xs"
                      disabled={busy || draft === 0}
                      onClick={() => moveBoundary.mutate({ index: b.index, deltaM: draft })}
                    >
                      Move
                    </button>
                  </div>
                </>
              ) : (
                <div className="text-[11px] text-amber-700">
                  Held: {b.blocked_by.join("; ")}
                </div>
              )}
            </li>
          );
        })}
      </ul>

      {moveBoundary.isError && (
        <p className="text-red-600 text-xs">{(moveBoundary.error as Error).message}</p>
      )}
    </div>
  );
}
