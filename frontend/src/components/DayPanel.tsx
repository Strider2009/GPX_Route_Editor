import { useState } from "react";
import type { DaySummary } from "../api/types";
import { useUIStore } from "../state/uiStore";
import {
  useDeleteDay,
  useMergeDays,
  useReverse,
  useRotate,
  useSetCircular,
  useReorderDays,
  useSetEndLocks,
  useSetLocked,
  useSplit,
  useSplitEven,
  useTrim,
  useUpdateDay,
} from "../api/hooks";

interface Props {
  projectId: number;
  days: DaySummary[];
}

export default function DayPanel({ projectId, days }: Props) {
  const selectedDayId = useUIStore((s) => s.selectedDayId);
  const setSelectedDay = useUIStore((s) => s.setSelectedDay);
  const selectedPointIndex = useUIStore((s) => s.selectedPointIndex);
  const rangeStart = useUIStore((s) => s.rangeStart);
  const setRangeStart = useUIStore((s) => s.setRangeStart);

  const setCircular = useSetCircular(projectId);
  const setLocked = useSetLocked(projectId);
  const setEndLocks = useSetEndLocks(projectId);
  const updateDay = useUpdateDay(projectId);
  const deleteDay = useDeleteDay(projectId);
  const rotate = useRotate(projectId);
  const trim = useTrim(projectId);
  const reverse = useReverse(projectId);
  const split = useSplit(projectId);
  const splitEven = useSplitEven(projectId);
  const mergeDays = useMergeDays(projectId);
  const reorder = useReorderDays(projectId);
  const [dragId, setDragId] = useState<number | null>(null);
  const [dropPos, setDropPos] = useState<number | null>(null);
  const [evenParts, setEvenParts] = useState(3);
  const [weightClimb, setWeightClimb] = useState(false);

  const sortedDays = [...days].sort((a, b) => a.order_index - b.order_index);
  const selectedDay = sortedDays.find((d) => d.id === selectedDayId) ?? null;
  const selectedPos = selectedDay ? sortedDays.findIndex((d) => d.id === selectedDay.id) : -1;
  // Merge joins to the following day; on the last day, join to the one before.
  const neighbour =
    selectedPos < 0
      ? null
      : (sortedDays[selectedPos + 1] ?? (selectedPos > 0 ? sortedDays[selectedPos - 1] : null));

  const handleDrop = (targetPos: number) => {
    setDropPos(null);
    if (dragId == null) return;
    const from = sortedDays.findIndex((d) => d.id === dragId);
    setDragId(null);
    if (from < 0 || from === targetPos) return;
    // Send the whole order at once rather than swapping pairs, so the server
    // never holds two days claiming the same position.
    const ids = sortedDays.map((d) => d.id);
    const [moved] = ids.splice(from, 1);
    ids.splice(targetPos, 0, moved);
    reorder.mutate(ids);
  };

  return (
    <div className="panel">
      <h2 className="panel-title">Days</h2>
      {sortedDays.length > 1 && (
        <p className="hint">Drag to reorder.</p>
      )}
      <ul className="flex flex-col gap-1">
        {sortedDays.map((day, position) => (
          <li
            key={day.id}
            draggable
            onDragStart={() => setDragId(day.id)}
            onDragEnd={() => {
              setDragId(null);
              setDropPos(null);
            }}
            onDragOver={(e) => {
              e.preventDefault();
              if (dragId != null && dragId !== day.id) setDropPos(position);
            }}
            onDrop={(e) => {
              e.preventDefault();
              handleDrop(position);
            }}
            className={`rounded-md border transition-colors ${
              day.id === selectedDayId
                ? "bg-brand-tint border-brand"
                : "border-line hover:border-ink-faint hover:bg-page"
            } ${dragId === day.id ? "opacity-40" : ""} ${
              dropPos === position && dragId !== day.id ? "border-brand border-dashed" : ""
            }`}
          >
            <div className="flex items-stretch">
              <span
                className="px-1 flex items-center text-ink-faint cursor-grab select-none"
                title="Drag to reorder"
              >
                ⠿
              </span>

              <button onClick={() => setSelectedDay(day.id)} className="flex-1 text-left py-1 min-w-0">
                <div className="flex items-center gap-1">
                  <span className="text-ink-faint text-xs shrink-0">{position + 1}.</span>
                  <span className="font-medium truncate">{day.name}</span>
                  {day.is_circular && (
                    <span className="chip shrink-0" title="Circular route">
                      loop
                    </span>
                  )}
                </div>
                <div className="text-xs text-ink-muted">
                  {(day.stats.distance_m / 1000).toFixed(1)} km &middot; +
                  {Math.round(day.stats.ascent_m)} m &middot; {day.stats.point_count} pts
                </div>
              </button>

              <div className="flex items-center gap-0.5 pr-1">
                <button
                  className={`px-1 py-0.5 rounded text-xs ${
                    day.is_locked ? "bg-amber-100 text-amber-800" : "text-ink-faint hover:text-ink-muted"
                  }`}
                  title={day.is_locked ? "Locked - click to unlock" : "Lock this day's route"}
                  onClick={() => setLocked.mutate({ dayId: day.id, value: !day.is_locked })}
                >
                  {day.is_locked ? "🔒" : "🔓"}
                </button>
                <button
                  className="px-1 py-0.5 rounded text-xs text-ink-faint hover:text-red-600"
                  title="Delete this day"
                  onClick={() => {
                    if (confirm(`Delete day "${day.name}"?`)) deleteDay.mutate(day.id);
                  }}
                >
                  ✕
                </button>
              </div>
            </div>
          </li>
        ))}
        {sortedDays.length === 0 && <li className="text-xs text-ink-muted">No days yet.</li>}
      </ul>

      {selectedDay && (
        <div className="mt-1 border-t border-line pt-3 flex flex-col gap-2">
          <input
            className="w-full text-sm font-medium"
            value={selectedDay.name}
            onChange={(e) => updateDay.mutate({ dayId: selectedDay.id, data: { name: e.target.value } })}
          />

          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={selectedDay.is_circular}
              onChange={(e) => setCircular.mutate({ dayId: selectedDay.id, value: e.target.checked })}
            />
            Circular route (loop)
          </label>
          {selectedDay.is_locked && (
            <p className="text-xs text-amber-600">
              This day is locked: the core route can't be changed. Add connectors below instead.
            </p>
          )}

          <div className="flex flex-col gap-1 border border-line rounded-md p-2">
            <div className="text-xs font-semibold text-ink">Pin the ends</div>
            <p className="hint">
              Holds a boundary in place without freezing the whole day.
            </p>
            <label className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                disabled={selectedDay.is_locked}
                checked={selectedDay.is_locked || selectedDay.lock_start}
                onChange={(e) =>
                  setEndLocks.mutate({ dayId: selectedDay.id, lock_start: e.target.checked })
                }
              />
              Pin start
            </label>
            <label className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                disabled={selectedDay.is_locked}
                checked={selectedDay.is_locked || selectedDay.lock_end}
                onChange={(e) =>
                  setEndLocks.mutate({ dayId: selectedDay.id, lock_end: e.target.checked })
                }
              />
              Pin end
            </label>
          </div>

          <div className="hint">Selected point: {selectedPointIndex ?? "none (click map or list)"}</div>

          {selectedDay.is_circular ? (
            <button
              disabled={selectedPointIndex == null || selectedDay.is_locked}
              className="btn"
              onClick={() => rotate.mutate({ dayId: selectedDay.id, index: selectedPointIndex! })}
            >
              Set selected point as start/end
            </button>
          ) : (
            <div className="flex flex-col gap-1">
              <button
                disabled={selectedPointIndex == null}
                className="btn"
                onClick={() => setRangeStart(selectedPointIndex)}
              >
                Mark range start ({rangeStart ?? "-"})
              </button>
              <button
                disabled={rangeStart == null || selectedPointIndex == null || selectedDay.is_locked}
                className="btn"
                onClick={() => {
                  trim.mutate({
                    dayId: selectedDay.id,
                    start_index: rangeStart!,
                    end_index: selectedPointIndex!,
                  });
                  setRangeStart(null);
                }}
              >
                Trim route to [{rangeStart ?? "-"} .. {selectedPointIndex ?? "-"}]
              </button>
            </div>
          )}

          <button disabled={selectedDay.is_locked} className="btn" onClick={() => reverse.mutate(selectedDay.id)}>
            Reverse direction
          </button>

          <button
            disabled={selectedPointIndex == null || selectedDay.is_locked}
            className="btn"
            onClick={() => split.mutate({ dayId: selectedDay.id, indices: [selectedPointIndex!] })}
          >
            Split into two days here
          </button>

          <div className="border border-line rounded-md p-2 flex flex-col gap-1">
            <div className="text-xs font-semibold text-ink">Split evenly</div>
            <div className="flex items-center gap-2 text-xs">
              <label className="flex items-center gap-1">
                into
                <input
                  type="number"
                  min={2}
                  max={20}
                  className="border border-line rounded-md px-1 py-0.5 w-14"
                  value={evenParts}
                  onChange={(e) => setEvenParts(Number(e.target.value))}
                />
                days
              </label>
              <button
                className="btn-primary"
                disabled={selectedDay.is_locked || splitEven.isPending}
                onClick={() =>
                  splitEven.mutate({
                    dayId: selectedDay.id,
                    parts: evenParts,
                    climbWeight: weightClimb ? 1 : 0,
                  })
                }
              >
                {splitEven.isPending ? "..." : "Split"}
              </button>
            </div>
            <label className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={weightClimb}
                onChange={(e) => setWeightClimb(e.target.checked)}
              />
              Shorten hilly days
            </label>
            {splitEven.isError && (
              <p className="text-red-600 text-xs">{(splitEven.error as Error).message}</p>
            )}
          </div>

          {neighbour && (
            <button
              className="btn"
              disabled={selectedDay.is_locked || neighbour.is_locked || mergeDays.isPending}
              onClick={() =>
                mergeDays.mutate(
                  { dayIdA: selectedDay.id, dayIdB: neighbour.id },
                  { onSuccess: (merged) => setSelectedDay(merged.id) }
                )
              }
            >
              {mergeDays.isPending ? "Merging..." : `Merge with "${neighbour.name.slice(0, 18)}"`}
            </button>
          )}
          {mergeDays.isError && (
            <p className="text-red-600 text-xs">{(mergeDays.error as Error).message}</p>
          )}

        </div>
      )}
    </div>
  );
}
