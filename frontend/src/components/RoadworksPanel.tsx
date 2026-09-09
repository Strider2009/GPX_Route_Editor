import { useEffect, useState } from "react";
import type { CyclingRelevance, RoadworkMatch } from "../api/types";
import {
  useClearRoadworks,
  useDayRoadworks,
  useFetchRoadworks,
  useRoadworksStatus,
} from "../api/hooks";
import { useUIStore } from "../state/uiStore";

interface Props {
  dayId: number;
  onMatchesChange: (matches: RoadworkMatch[]) => void;
}

export const RELEVANCE_COLORS: Record<CyclingRelevance, string> = {
  high: "#dc2626",
  medium: "#f59e0b",
  low: "#6b7280",
  none: "#d1d5db",
};

const METRES_PER_MILE = 1609.344;

const RELEVANCE_ORDER: Record<CyclingRelevance, number> = { high: 3, medium: 2, low: 1, none: 0 };

function formatDistance(m: number): string {
  if (m < 1000) return `${Math.round(m)}m`;
  return `${(m / METRES_PER_MILE).toFixed(1)}mi`;
}

function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export default function RoadworksPanel({ dayId, onMatchesChange }: Props) {
  const [targetDate, setTargetDate] = useState(today());
  const [bufferM, setBufferM] = useState(100);
  const [sortBy, setSortBy] = useState<"distance" | "relevance">("distance");
  const [minRelevance, setMinRelevance] = useState("medium");
  const [tileZoom, setTileZoom] = useState(11);
  const [active, setActive] = useState(false);

  const setSelectedPoint = useUIStore((s) => s.setSelectedPoint);

  const status = useRoadworksStatus();
  const fetchRoadworks = useFetchRoadworks();
  const clearRoadworks = useClearRoadworks();

  const query = useDayRoadworks(
    dayId,
    { targetDate: targetDate || undefined, bufferM, minRelevance },
    active
  );

  // Sorted here rather than refetching, so switching order is instant.
  const matches = [...(query.data?.matches ?? [])].sort((a, b) =>
    sortBy === "distance"
      ? a.distance_m - b.distance_m
      : RELEVANCE_ORDER[b.cycling_relevance] - RELEVANCE_ORDER[a.cycling_relevance] ||
        a.distance_m - b.distance_m
  );
  // Hand results to the parent so the map can draw them.
  useEffect(() => {
    onMatchesChange(matches);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query.data]);

  // Checking a different day shouldn't show the previous day's results.
  useEffect(() => {
    setActive(false);
    onMatchesChange([]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dayId]);

  const busy = fetchRoadworks.isPending || query.isFetching;

  const checkRoute = async () => {
    try {
      await fetchRoadworks.mutateAsync({ dayId, z: tileZoom, targetDate: targetDate || undefined });
    } catch {
      return; // the error is surfaced from the mutation below
    }
    setActive(true);
  };

  const fetched = fetchRoadworks.data;

  return (
    <div className="panel">
      <h3 className="panel-title">Roadworks</h3>

      <div className="flex flex-col gap-1">
        <label className="text-xs flex items-center justify-between gap-2">
          On date
          <input
            type="date"
            className="border border-line rounded-md px-1 py-0.5"
            value={targetDate}
            onChange={(e) => setTargetDate(e.target.value)}
          />
        </label>
        <label className="text-xs flex items-center justify-between gap-2">
          Within
          <span className="flex items-center gap-1">
            <input
              type="number"
              min={0}
              max={25000}
              step={50}
              className="border border-line rounded-md px-1 py-0.5 w-20"
              value={bufferM}
              onChange={(e) => setBufferM(Number(e.target.value))}
            />
            <span className="text-ink-muted">m</span>
          </span>
        </label>
        <div className="flex gap-1">
          {[50, 100, 250, 500].map((m) => (
            <button
              key={m}
              className={`text-[11px] px-1.5 py-0.5 rounded border ${
                bufferM === m ? "bg-brand-tint border-brand" : "border-line hover:bg-page"
              }`}
              onClick={() => setBufferM(m)}
            >
              {m}m
            </button>
          ))}
          <button
            className={`text-[11px] px-1.5 py-0.5 rounded border ${
              bufferM === 8047 ? "bg-brand-tint border-brand" : "border-line hover:bg-page"
            }`}
            onClick={() => setBufferM(8047)}
          >
            5mi
          </button>
        </div>
        <label className="text-xs flex items-center justify-between gap-2">
          Show
          <select
            className="border border-line rounded-md px-1 py-0.5"
            value={minRelevance}
            onChange={(e) => setMinRelevance(e.target.value)}
          >
            <option value="high">Closures &amp; detours only</option>
            <option value="medium">+ obstructions</option>
            <option value="low">Everything relevant</option>
            <option value="none">Everything</option>
          </select>
        </label>
        <label className="text-xs flex items-center justify-between gap-2">
          Sort by
          <select
            className="border border-line rounded-md px-1 py-0.5"
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as "distance" | "relevance")}
          >
            <option value="distance">Distance to route</option>
            <option value="relevance">Severity</option>
          </select>
        </label>

        <button className="btn-teal" disabled={busy} onClick={checkRoute}>
          {fetchRoadworks.isPending ? "Fetching tiles..." : query.isFetching ? "Checking..." : "Check route"}
        </button>
      </div>

      {fetchRoadworks.isError && (
        <p className="text-red-600 text-xs">{(fetchRoadworks.error as Error).message}</p>
      )}
      {query.isError && <p className="text-red-600 text-xs">{(query.error as Error).message}</p>}

      {fetched && (
        <div className="hint">
          {fetched.tiles_required} tiles for this route: {fetched.tiles_from_cache} cached,{" "}
          {fetched.tiles_fetched} fetched
          {fetched.tiles_empty > 0 && `, ${fetched.tiles_empty} empty`}
          {fetched.failures.length > 0 && (
            <span className="text-amber-700"> · {fetched.failures.length} failed</span>
          )}
        </div>
      )}

      {active && query.data && (
        <div className="flex flex-col gap-1">
          {query.data.total_stored === 0 ? (
            <div className="text-xs bg-amber-50 border border-amber-200 rounded p-2 text-amber-800">
              Nothing came back for this route. The tile server may have had no data for that date.
            </div>
          ) : (
            <div className="text-xs text-ink-muted">
              {matches.length} hit{matches.length === 1 ? "" : "s"} within {formatDistance(bufferM)} of
              the route on {targetDate}
            </div>
          )}
          <ul className="flex flex-col gap-1 max-h-72 overflow-y-auto">
            {matches.map((m) => (
              <li
                key={m.external_id}
                className="border border-line rounded-md px-2 py-1 cursor-pointer hover:bg-page"
                onClick={() => setSelectedPoint(m.nearest_point_index)}
              >
                <div className="flex items-center justify-between gap-1">
                  <span className="font-medium truncate">{m.road_name || "(unnamed road)"}</span>
                  <span
                    className="text-[10px] px-1 rounded text-white shrink-0"
                    style={{ background: RELEVANCE_COLORS[m.cycling_relevance] }}
                  >
                    {formatDistance(m.distance_m)}
                  </span>
                </div>
                <div className="text-xs text-ink-muted">{m.traffic_management || "Works"}</div>
                {m.works_desc && <div className="text-[11px] text-ink-muted line-clamp-2">{m.works_desc}</div>}
                <div className="text-[11px] text-ink-faint">
                  {(m.start_date || "").slice(0, 10)} &rarr; {(m.end_date || "").slice(0, 10)}
                  {m.works_state ? ` · ${m.works_state}` : ""}
                </div>
              </li>
            ))}
            {matches.length === 0 && query.data.total_stored > 0 && (
              <li className="text-xs text-ink-muted">
                Nothing relevant on this route. Try a wider radius, or set "Show" to Everything.
              </li>
            )}
          </ul>
        </div>
      )}

      <div className="text-[11px] text-ink-faint border-t border-line pt-1 flex items-center gap-2 flex-wrap">
        <span>
          {status.data
            ? `${status.data.total} works · ${status.data.cached_tiles} tiles cached (${Math.round(
                status.data.cached_bytes / 1024
              )} KB)`
            : "..."}
        </span>
        <label className="flex items-center gap-1">
          zoom
          <input
            type="number"
            min={8}
            max={14}
            className="border border-line rounded-md px-1 w-12"
            value={tileZoom}
            onChange={(e) => setTileZoom(Number(e.target.value))}
          />
        </label>
        {status.data && status.data.cached_tiles > 0 && (
          <button
            className="text-red-600 hover:underline"
            onClick={() => {
              if (confirm("Clear cached tiles and imported works?")) clearRoadworks.mutate();
            }}
          >
            clear cache
          </button>
        )}
      </div>
    </div>
  );
}
