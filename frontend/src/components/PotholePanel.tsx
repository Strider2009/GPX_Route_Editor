import { useEffect, useState } from "react";
import type { PotholeMatch } from "../api/types";
import { useClearPotholes, useDayPotholes, useFetchPotholes, usePotholeStatus } from "../api/hooks";
import { useUIStore } from "../state/uiStore";

interface Props {
  dayId: number;
  onMatchesChange: (matches: PotholeMatch[]) => void;
}

export const POTHOLE_COLOR = "#7c3aed";

export default function PotholePanel({ dayId, onMatchesChange }: Props) {
  const [bufferM, setBufferM] = useState(25);
  const [maxAgeYears, setMaxAgeYears] = useState(2);
  const [zoom, setZoom] = useState(12);
  const [active, setActive] = useState(false);

  const setSelectedPoint = useUIStore((s) => s.setSelectedPoint);
  const status = usePotholeStatus();
  const fetchPotholes = useFetchPotholes();
  const clearPotholes = useClearPotholes();
  const query = useDayPotholes(dayId, { bufferM, maxAgeYears }, active);

  const matches = query.data?.matches ?? [];
  useEffect(() => {
    onMatchesChange(matches);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query.data]);

  useEffect(() => {
    setActive(false);
    onMatchesChange([]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dayId]);

  const busy = fetchPotholes.isPending || query.isFetching;
  const fetched = fetchPotholes.data;

  const check = async () => {
    try {
      await fetchPotholes.mutateAsync({ dayId, z: zoom });
    } catch {
      return;
    }
    setActive(true);
  };

  return (
    <div className="panel">
      <h3 className="panel-title">Potholes</h3>
      <p className="hint">
        Reports made via FixMyStreet. Many stay "open" simply because nobody closed them, so old
        ones are usually long since filled - the age limit matters more than the distance.
      </p>

      <div className="flex flex-col gap-1">
        <label className="text-xs flex items-center justify-between gap-2">
          Within (m)
          <input
            type="number"
            min={0}
            max={2000}
            step={25}
            className="border border-line rounded-md px-1 py-0.5 w-20"
            value={bufferM}
            onChange={(e) => setBufferM(Number(e.target.value))}
          />
        </label>
        <label className="text-xs flex items-center justify-between gap-2">
          Reported within (years)
          <input
            type="number"
            min={0.5}
            max={25}
            step={0.5}
            className="border border-line rounded-md px-1 py-0.5 w-20"
            value={maxAgeYears}
            onChange={(e) => setMaxAgeYears(Number(e.target.value))}
          />
        </label>
        <button className="btn-teal" disabled={busy} onClick={check}>
          {fetchPotholes.isPending ? "Fetching..." : query.isFetching ? "Checking..." : "Check potholes"}
        </button>
      </div>

      {fetchPotholes.isError && (
        <p className="text-red-600 text-xs">{(fetchPotholes.error as Error).message}</p>
      )}
      {query.isError && <p className="text-red-600 text-xs">{(query.error as Error).message}</p>}

      {fetched && (
        <div className="hint">
          {fetched.boxes_required} boxes: {fetched.boxes_cached} cached, {fetched.boxes_fetched}{" "}
          fetched · {fetched.new_reports} new reports
          {fetched.boxes_saturated > 0 && (
            <span className="text-amber-700">
              {" "}
              · {fetched.boxes_saturated} box(es) hit the 100-report cap, so some were missed - try a
              higher zoom
            </span>
          )}
        </div>
      )}

      {active && query.data && (
        <div className="flex flex-col gap-1">
          <div className="text-xs text-ink-muted">
            {matches.length} within {bufferM}m reported in the last {maxAgeYears} year
            {maxAgeYears === 1 ? "" : "s"}
            {query.data.excluded_too_old > 0 && (
              <span className="text-ink-faint"> ({query.data.excluded_too_old} older ones hidden)</span>
            )}
          </div>
          <ul className="flex flex-col gap-1 max-h-64 overflow-y-auto">
            {matches.map((m) => (
              <li
                key={m.report_id}
                className="border border-line rounded-md px-2 py-1 cursor-pointer hover:bg-page"
                onClick={() => setSelectedPoint(m.nearest_point_index)}
              >
                <div className="flex items-center justify-between gap-1">
                  <span className="font-medium truncate">{m.title || "Pothole"}</span>
                  <span
                    className="text-[10px] px-1 rounded text-white shrink-0"
                    style={{ background: POTHOLE_COLOR }}
                  >
                    {Math.round(m.distance_m)}m
                  </span>
                </div>
                <div className="text-[11px] text-ink-faint flex items-center gap-2">
                  <span>~{m.reported_approx ?? "unknown date"}</span>
                  <a
                    className="text-brand hover:underline"
                    href={m.url ?? "#"}
                    target="_blank"
                    rel="noreferrer"
                    onClick={(e) => e.stopPropagation()}
                  >
                    report
                  </a>
                </div>
              </li>
            ))}
            {matches.length === 0 && (
              <li className="text-xs text-ink-muted">
                None reported recently on this route. Try a longer age limit.
              </li>
            )}
          </ul>
        </div>
      )}

      <div className="text-[11px] text-ink-faint border-t border-line pt-1 flex items-center gap-2 flex-wrap">
        <span>{status.data ? `${status.data.total} reports stored` : "..."}</span>
        <label className="flex items-center gap-1">
          zoom
          <input
            type="number"
            min={10}
            max={15}
            className="border border-line rounded-md px-1 w-12"
            value={zoom}
            onChange={(e) => setZoom(Number(e.target.value))}
          />
        </label>
        {status.data && status.data.total > 0 && (
          <button
            className="text-red-600 hover:underline"
            onClick={() => {
              if (confirm("Clear stored pothole reports?")) clearPotholes.mutate();
            }}
          >
            clear
          </button>
        )}
      </div>
    </div>
  );
}
