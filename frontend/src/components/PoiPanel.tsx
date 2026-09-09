import { useState } from "react";
import type { DayDetail, Poi } from "../api/types";
import { useAddPoi, useDeletePoi, useUpdatePoi } from "../api/hooks";

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

  const addPoi = useAddPoi(projectId, day.id);
  const updatePoi = useUpdatePoi(projectId, day.id);
  const deletePoi = useDeletePoi(projectId, day.id);

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

  const startRename = (p: Poi) => {
    setEditingId(p.id);
    setEditName(p.name);
  };

  const saveRename = () => {
    if (editingId == null || !editName.trim()) return;
    updatePoi.mutate({ poiId: editingId, name: editName.trim() }, { onSuccess: () => setEditingId(null) });
  };

  return (
    <div className="panel">
      <h3 className="panel-title">Points of interest</h3>
      <p className="text-xs text-ink-muted">
        Cafes, water stops and anything else worth marking. They export as GPX waypoints, so they
        sit beside the route rather than in it &mdash; locking the day, or trimming and splitting
        it, leaves them where you put them.
      </p>

      <ul className="flex flex-col gap-1">
        {day.pois.map((p) => (
          <li key={p.id} className="border border-line rounded-md px-2 py-1">
            {editingId === p.id ? (
              <div className="flex flex-col gap-1">
                <input
                  className="border border-line rounded-md px-2 py-1"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && saveRename()}
                  autoFocus
                />
                <div className="flex gap-2">
                  <button className="btn-primary" onClick={saveRename}>
                    Save
                  </button>
                  <button className="btn" onClick={() => setEditingId(null)}>
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between gap-1">
                  <span className="font-medium truncate">{p.name}</span>
                  {p.symbol && <span className="text-xs text-ink-muted shrink-0">{p.symbol}</span>}
                </div>
                {p.notes && <div className="text-xs text-ink-muted">{p.notes}</div>}
                <div className="text-xs text-ink-muted">
                  {p.lat.toFixed(5)}, {p.lon.toFixed(5)}
                </div>
                <div className="flex gap-2 mt-1 flex-wrap">
                  <button className="btn" onClick={() => startRename(p)}>
                    Rename
                  </button>
                  <button className="btn-danger" onClick={() => deletePoi.mutate(p.id)}>
                    Delete
                  </button>
                </div>
              </>
            )}
          </li>
        ))}
        {day.pois.length === 0 && <li className="text-xs text-ink-muted">No POIs yet.</li>}
      </ul>

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
          <datalist id="poi-symbols">
            {SYMBOLS.map((s) => (
              <option key={s} value={s} />
            ))}
          </datalist>
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
