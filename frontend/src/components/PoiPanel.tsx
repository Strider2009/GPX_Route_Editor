import { useEffect, useMemo, useRef, useState } from "react";
import type { DayDetail, Poi } from "../api/types";
import { useAddPoi, useDeletePoi, useDescribePois, useUpdatePoi } from "../api/hooks";
import { cumulativeDistances, haversine } from "../lib/geo";
import { useUIStore } from "../state/uiStore";

interface Props {
  projectId: number;
  day: DayDetail;
  /** Where the user last clicked while placing, or null if nothing is pending. */
  pendingPoi: { lat: number; lon: number } | null;
  setPendingPoi: (p: { lat: number; lon: number } | null) => void;
  placing: boolean;
  setPlacing: (v: boolean) => void;
}

/** A short list of the <sym> values devices most often recognise. Free text is
 *  still allowed, because every manufacturer supports a different set. */
const SYMBOLS = [
  "Restaurant",
  "Drinking Water",
  "Lodging",
  "Convenience Store",
  "Parking Area",
  "Restroom",
  "Scenic Area",
  "Bike Trail",
];

/** How far along the day each POI sits, by its nearest route point. */
function kmAlong(day: DayDetail): Map<number, number> {
  const out = new Map<number, number>();
  if (day.points.length === 0) return out;
  const cumulative = cumulativeDistances(day.points);
  for (const poi of day.pois) {
    let best = 0;
    let bestD = Infinity;
    day.points.forEach((pt, i) => {
      const d = haversine(pt, poi);
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    });
    out.set(poi.id, cumulative[best] / 1000);
  }
  return out;
}

export default function PoiPanel({
  projectId,
  day,
  pendingPoi,
  setPendingPoi,
  placing,
  setPlacing,
}: Props) {
  const [name, setName] = useState("");
  const [symbol, setSymbol] = useState(SYMBOLS[0]);
  const [notes, setNotes] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editSymbol, setEditSymbol] = useState("");
  const [editNotes, setEditNotes] = useState("");

  const selectedPoiId = useUIStore((s) => s.selectedPoiId);
  const selectPoi = useUIStore((s) => s.selectPoi);
  const rowRefs = useRef(new Map<number, HTMLLIElement>());

  const km = useMemo(() => kmAlong(day), [day]);
  // In the order you ride past them, which is how you look for one.
  const ordered = useMemo(
    () => [...day.pois].sort((a, b) => (km.get(a.id) ?? 0) - (km.get(b.id) ?? 0)),
    [day.pois, km]
  );

  // Picked on the map: bring its row into view in the sidebar.
  useEffect(() => {
    if (selectedPoiId == null) return;
    rowRefs.current.get(selectedPoiId)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [selectedPoiId]);

  const addPoi = useAddPoi(projectId, day.id);
  const updatePoi = useUpdatePoi(projectId, day.id);
  const deletePoi = useDeletePoi(projectId, day.id);
  const describePois = useDescribePois(projectId, day.id);

  const cancel = () => {
    setPlacing(false);
    setPendingPoi(null);
    setName("");
    setNotes("");
  };

  const save = () => {
    if (!pendingPoi || !name.trim()) return;
    addPoi.mutate(
      {
        name: name.trim(),
        lat: pendingPoi.lat,
        lon: pendingPoi.lon,
        symbol: symbol || null,
        notes: notes.trim() || null,
      },
      { onSuccess: cancel }
    );
  };

  const startEdit = (p: Poi) => {
    setEditingId(p.id);
    setEditName(p.name);
    setEditSymbol(p.symbol ?? "");
    setEditNotes(p.notes ?? "");
  };

  const saveEdit = () => {
    if (editingId == null || !editName.trim()) return;
    updatePoi.mutate(
      // Empty strings rather than null: the API treats null as "leave unchanged".
      { poiId: editingId, name: editName.trim(), symbol: editSymbol.trim(), notes: editNotes.trim() },
      { onSuccess: () => setEditingId(null) }
    );
  };

  return (
    <div className="panel">
      <h3 className="panel-title">Points of interest</h3>
      <p className="text-xs text-ink-muted">
        Cafes, water stops and anything else worth marking. They export as GPX waypoints, so they
        sit beside the route rather than in it &mdash; locking the day, or trimming and splitting
        it, leaves them where you put them.
      </p>

      {day.pois.length > 0 && (
        <div className="flex flex-col gap-1">
          <button
            className="btn self-start"
            onClick={() => describePois.mutate()}
            disabled={describePois.isPending}
            title="Rename markers called 'Waypoint' after the junction, landmark and town they sit at, and fill empty notes. Names you typed are kept."
          >
            {describePois.isPending ? "Describing…" : "Describe waypoints"}
          </button>
          {describePois.isError && (
            <p className="text-xs text-red-600">{(describePois.error as Error).message}</p>
          )}
          {describePois.data && (
            <p className="text-xs text-ink-muted">
              {describePois.data.updated === 0
                ? "Every waypoint already has a name and notes."
                : `Described ${describePois.data.updated} waypoint${describePois.data.updated === 1 ? "" : "s"}.`}
              {describePois.data.places_error && " Town names were unavailable; try again later to add them."}
            </p>
          )}
        </div>
      )}

      <ul className="flex flex-col gap-1 max-h-96 overflow-y-auto">
        {ordered.map((p) => {
          const selected = p.id === selectedPoiId;
          const at = km.get(p.id);
          return (
            <li
              key={p.id}
              ref={(el) => {
                if (el) rowRefs.current.set(p.id, el);
                else rowRefs.current.delete(p.id);
              }}
              className={`border rounded-md ${selected ? "border-brand bg-brand-tint" : "border-line"}`}
            >
              <button
                className="w-full flex items-center justify-between gap-2 px-2 py-1 text-left"
                onClick={() => selectPoi(selected ? null : p.id, true)}
                title={selected ? "Hide details" : "Show details and find it on the map"}
              >
                <span className="font-medium truncate">{p.name}</span>
                {at != null && <span className="text-xs text-ink-muted shrink-0">{at.toFixed(1)} km</span>}
              </button>

              {selected &&
                (editingId === p.id ? (
                  <div className="flex flex-col gap-1 px-2 pb-2">
                    <input
                      className="border border-line rounded-md px-2 py-1"
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && saveEdit()}
                      placeholder="Name"
                      autoFocus
                    />
                    <input
                      className="border border-line rounded-md px-2 py-1"
                      list="poi-symbols"
                      value={editSymbol}
                      onChange={(e) => setEditSymbol(e.target.value)}
                      placeholder="Symbol (optional)"
                    />
                    <textarea
                      className="border border-line rounded-md px-2 py-1 text-sm"
                      rows={4}
                      value={editNotes}
                      onChange={(e) => setEditNotes(e.target.value)}
                      placeholder="Notes (optional)"
                    />
                    <div className="flex gap-2">
                      <button className="btn-primary" onClick={saveEdit} disabled={!editName.trim()}>
                        Save
                      </button>
                      <button className="btn" onClick={() => setEditingId(null)}>
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-col gap-1 px-2 pb-2 text-xs text-ink-muted">
                    {p.symbol && (
                      <div>
                        <span className="text-ink-faint">Symbol:</span> {p.symbol}
                      </div>
                    )}
                    {p.notes ? (
                      <p className="text-ink whitespace-pre-line">{p.notes}</p>
                    ) : (
                      <p className="italic">No notes. "Describe waypoints" can fill them in.</p>
                    )}
                    <div>
                      {p.ele != null && <>{Math.round(p.ele)} m &middot; </>}
                      {p.lat.toFixed(5)}, {p.lon.toFixed(5)}
                    </div>
                    <div className="flex gap-2 mt-1 flex-wrap">
                      <button className="btn" onClick={() => startEdit(p)}>
                        Edit
                      </button>
                      <button className="btn-danger" onClick={() => deletePoi.mutate(p.id)}>
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
            </li>
          );
        })}
        {day.pois.length === 0 && <li className="text-xs text-ink-muted">No POIs yet.</li>}
      </ul>
      {/* Shared by the add and edit forms. */}
      <datalist id="poi-symbols">
        {SYMBOLS.map((s) => (
          <option key={s} value={s} />
        ))}
      </datalist>

      {placing ? (
        <div className="flex flex-col gap-1 border border-line rounded-md p-2">
          {pendingPoi ? (
            <p className="text-xs text-ink-muted">
              Placed at {pendingPoi.lat.toFixed(5)}, {pendingPoi.lon.toFixed(5)}. Click the map
              again to move it.
            </p>
          ) : (
            <p className="text-xs text-ink-muted">Click on the map to place the POI.</p>
          )}
          <input
            className="border border-line rounded-md px-2 py-1"
            placeholder="Name (e.g. Boston Tea Party)"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <input
            className="border border-line rounded-md px-2 py-1"
            list="poi-symbols"
            placeholder="Symbol (optional)"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
          />
          <input
            className="border border-line rounded-md px-2 py-1"
            placeholder="Notes (optional, e.g. opens 08:00)"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
          <div className="flex gap-2 flex-wrap">
            <button className="btn-primary" onClick={save} disabled={!pendingPoi || !name.trim()}>
              Save POI
            </button>
            <button className="btn" onClick={cancel}>
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button className="btn-primary self-start" onClick={() => setPlacing(true)}>
          + Add POI
        </button>
      )}
    </div>
  );
}
