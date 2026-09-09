import { useEffect, useState } from "react";
import type { DayDetail, VenueKind, VenueSearchResult } from "../api/types";
import { useAddVenueAsPoi, useSetVenuePreferred, useVenueSearch } from "../api/hooks";
import { useUIStore } from "../state/uiStore";
import { SUMMARISED_TAGS, venueFacts } from "../lib/venueFacts";

interface Props {
  projectId: number;
  day: DayDetail;
  onResultsChange: (venues: VenueSearchResult[]) => void;
}

const KIND_LABEL: Record<VenueKind, string> = {
  cafe: "Cafes",
  food: "Food & pubs",
  water: "Water",
  toilets: "Toilets",
  bicycle: "Bike shops",
};

const RADII = [250, 500, 1000, 2000];

export default function VenuePanel({ projectId, day, onResultsChange }: Props) {
  const selectedPointIndex = useUIStore((s) => s.selectedPointIndex);
  const setSelectedPoint = useUIStore((s) => s.setSelectedPoint);

  const [radiusM, setRadiusM] = useState(500);
  const [kinds, setKinds] = useState<VenueKind[]>(["cafe", "water", "toilets"]);
  const [onlyPreferred, setOnlyPreferred] = useState(false);
  // Searching is deliberately explicit. Every miss costs somebody else's donated
  // Overpass capacity, so selecting a point must not fire a request on its own.
  const [searchAt, setSearchAt] = useState<number | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);

  const search = useVenueSearch(
    day.id,
    { pointIndex: searchAt ?? 0, radiusM, kinds },
    searchAt !== null
  );
  const setPreferred = useSetVenuePreferred();
  const addVenue = useAddVenueAsPoi(projectId, day.id);

  const toggleKind = (k: VenueKind) =>
    setKinds((cur) => (cur.includes(k) ? cur.filter((x) => x !== k) : [...cur, k]));

  const runSearch = () => {
    if (selectedPointIndex == null) return;
    setSearchAt(selectedPointIndex);
  };

  const results = search.data?.venues ?? [];
  const shown = onlyPreferred ? results.filter((v) => v.preferred) : results;

  // Hand results to the parent so the map can draw them. Keyed on the query data
  // rather than on `shown`, which is a fresh array every render.
  useEffect(() => {
    onResultsChange(shown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search.data, onlyPreferred]);

  // Looking at a different day shouldn't leave the previous day's pins on the map.
  useEffect(() => {
    setSearchAt(null);
    onResultsChange([]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [day.id]);

  return (
    <div className="panel">
      <h3 className="panel-title">Find places nearby</h3>

      {selectedPointIndex == null ? (
        <p className="text-xs text-ink-muted">
          Select a point on the route, then search around it.
        </p>
      ) : (
        <p className="text-xs text-ink-muted">
          Searching around point {selectedPointIndex + 1} of {day.points.length}.
        </p>
      )}

      <div className="flex flex-wrap gap-1">
        {(Object.keys(KIND_LABEL) as VenueKind[]).map((k) => (
          <button
            key={k}
            className={kinds.includes(k) ? "btn-primary" : "btn"}
            onClick={() => toggleKind(k)}
          >
            {KIND_LABEL[k]}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        <label className="text-xs text-ink-muted">Radius</label>
        <select
          className="border border-line rounded-md px-2 py-1"
          value={radiusM}
          onChange={(e) => setRadiusM(Number(e.target.value))}
        >
          {RADII.map((r) => (
            <option key={r} value={r}>
              {r < 1000 ? `${r} m` : `${r / 1000} km`}
            </option>
          ))}
        </select>
        <button
          className="btn-primary"
          onClick={runSearch}
          disabled={selectedPointIndex == null || kinds.length === 0 || search.isFetching}
        >
          {search.isFetching ? "Searching..." : "Search"}
        </button>
      </div>

      {search.error && (
        <p className="text-xs text-red-600">{(search.error as Error).message}</p>
      )}

      {search.data && (
        <div className="text-xs text-ink-muted flex items-center justify-between gap-2">
          <span>
            {search.data.count} found
            {search.data.from_cache && " (cached, no request sent)"}
          </span>
          <label className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={onlyPreferred}
              onChange={(e) => setOnlyPreferred(e.target.checked)}
            />
            Preferred only
          </label>
        </div>
      )}

      <ul className="flex flex-col gap-1 max-h-80 overflow-y-auto">
        {shown.map((v) => (
          <li key={v.id} className="border border-line rounded-md px-2 py-1">
            <div className="flex items-center justify-between gap-1">
              <span className="font-medium truncate">
                {v.preferred && <span title="Preferred">★ </span>}
                {v.name}
              </span>
              <span className="text-xs text-ink-muted shrink-0">{Math.round(v.distance_m)} m</span>
            </div>
            <div className="text-xs text-ink-muted">
              {KIND_LABEL[v.kind]} · {Math.round(v.distance_to_route_m)} m off route
            </div>
            {v.tags.opening_hours && (
              <div className="text-xs text-ink-muted truncate" title={v.tags.opening_hours}>
                {v.tags.opening_hours}
              </div>
            )}

            <div className="flex flex-wrap gap-1 mt-1">
              {venueFacts(v.kind, v.tags).map((f) => (
                <span
                  key={f.label}
                  className={
                    "text-xs rounded px-1 " +
                    (f.tone === "good"
                      ? "bg-green-100 text-green-800"
                      : f.tone === "warn"
                        ? "bg-amber-100 text-amber-800"
                        : "bg-gray-100 text-ink-muted")
                  }
                >
                  {f.label}
                </span>
              ))}
            </div>

            {v.tags.description && (
              <div className="text-xs text-ink-muted mt-1">{v.tags.description}</div>
            )}
            {v.tags.address && <div className="text-xs text-ink-muted">{v.tags.address}</div>}
            {v.user_note && <div className="text-xs text-ink-muted">{v.user_note}</div>}

            {expanded === v.id && (
              <dl className="text-xs text-ink-muted mt-1 border-t border-line pt-1">
                {Object.entries(v.tags)
                  .filter(([k]) => !SUMMARISED_TAGS.has(k))
                  .map(([k, val]) => (
                    <div key={k} className="flex gap-2">
                      <dt className="shrink-0 font-medium">{k}</dt>
                      <dd className="truncate">{val}</dd>
                    </div>
                  ))}
                <div className="flex gap-2">
                  <dt className="shrink-0 font-medium">osm</dt>
                  <dd>
                    <a
                      href={`https://www.openstreetmap.org/${v.external_id}`}
                      target="_blank"
                      rel="noreferrer"
                      className="underline"
                    >
                      {v.external_id}
                    </a>
                  </dd>
                </div>
              </dl>
            )}
            <div className="flex gap-2 mt-1 flex-wrap">
              <button
                className="btn"
                onClick={() => setSelectedPoint(v.nearest_point_index)}
                title="Jump to the closest point on the route"
              >
                Show
              </button>
              <button
                className="btn"
                onClick={() => setPreferred.mutate({ venueId: v.id, value: !v.preferred })}
              >
                {v.preferred ? "Unprefer" : "Prefer"}
              </button>
              <button className="btn-primary" onClick={() => addVenue.mutate({ venueId: v.id })}>
                Add to route
              </button>
              {v.tags.website && (
                <a className="btn" href={v.tags.website} target="_blank" rel="noreferrer">
                  Website
                </a>
              )}
              <button className="btn" onClick={() => setExpanded(expanded === v.id ? null : v.id)}>
                {expanded === v.id ? "Less" : "Details"}
              </button>
            </div>
          </li>
        ))}
        {search.data && shown.length === 0 && (
          <li className="text-xs text-ink-muted">
            {onlyPreferred ? "None of these are preferred yet." : "Nothing found in that radius."}
          </li>
        )}
      </ul>

      <p className="text-xs text-ink-muted">
        Places from OpenStreetMap contributors, ODbL. Results are cached, so searching the same
        spot again costs no request.
      </p>
    </div>
  );
}
