import { useState } from "react";
import type { Connector, ConnectorType, DayDetail, Point } from "../api/types";
import { useAddConnector, useDeleteConnector, useUpdateConnector } from "../api/hooks";

interface Props {
  projectId: number;
  day: DayDetail;
  draftPoints: Point[];
  setDraftPoints: (p: Point[]) => void;
  drawingConnectorId: number | "new" | null;
  setDrawingConnectorId: (id: number | "new" | null) => void;
}

const TYPE_LABEL: Record<ConnectorType, string> = {
  start_access: "Access to start (e.g. from hotel)",
  end_access: "Access from end (e.g. to hotel)",
  spur: "Detour / spur (e.g. to a cafe)",
};

export default function ConnectorPanel({
  projectId,
  day,
  draftPoints,
  setDraftPoints,
  drawingConnectorId,
  setDrawingConnectorId,
}: Props) {
  const [newName, setNewName] = useState("");
  const [newType, setNewType] = useState<ConnectorType>("spur");

  const addConnector = useAddConnector(projectId, day.id);
  const updateConnector = useUpdateConnector(day.id);
  const deleteConnector = useDeleteConnector(day.id);

  const startDrawingNew = () => {
    setDraftPoints([]);
    setDrawingConnectorId("new");
  };

  const startEditing = (c: Connector) => {
    setDraftPoints(c.points);
    setDrawingConnectorId(c.id);
  };

  const cancelDrawing = () => {
    setDraftPoints([]);
    setDrawingConnectorId(null);
  };

  const saveNew = () => {
    if (!newName.trim() || draftPoints.length === 0) return;
    addConnector.mutate(
      { name: newName.trim(), type: newType, points: draftPoints },
      {
        onSuccess: () => {
          setNewName("");
          cancelDrawing();
        },
      }
    );
  };

  const saveEdit = (connectorId: number) => {
    updateConnector.mutate({ connectorId, points: draftPoints }, { onSuccess: cancelDrawing });
  };

  return (
    <div className="panel">
      <h3 className="panel-title">Connectors (hotel / cafe access)</h3>
      <p className="text-xs text-ink-muted">
        Connectors are never affected by locking the core route, so you can add navigation legs
        without changing the locked route.
      </p>

      <ul className="flex flex-col gap-1">
        {day.connectors.map((c) => (
          <li key={c.id} className="border border-line rounded-md px-2 py-1">
            <div className="flex items-center justify-between gap-1">
              <span className="font-medium truncate">{c.name}</span>
              <span className="text-xs text-ink-muted shrink-0">{c.points.length} pts</span>
            </div>
            <div className="text-xs text-ink-muted">{TYPE_LABEL[c.type]}</div>
            <div className="flex gap-2 mt-1 flex-wrap">
              {drawingConnectorId === c.id ? (
                <>
                  <button className="btn" onClick={() => saveEdit(c.id)}>
                    Save
                  </button>
                  <button className="btn" onClick={cancelDrawing}>
                    Cancel
                  </button>
                  <button className="btn" onClick={() => setDraftPoints(draftPoints.slice(0, -1))}>
                    Undo point
                  </button>
                </>
              ) : (
                <button className="btn" onClick={() => startEditing(c)}>
                  Edit points
                </button>
              )}
              <button className="btn-danger" onClick={() => deleteConnector.mutate(c.id)}>
                Delete
              </button>
            </div>
          </li>
        ))}
        {day.connectors.length === 0 && <li className="text-xs text-ink-muted">No connectors yet.</li>}
      </ul>

      {drawingConnectorId === "new" ? (
        <div className="flex flex-col gap-1 border border-line rounded-md p-2">
          <input
            className="border border-line rounded-md px-2 py-1"
            placeholder="Name (e.g. Premier Inn access)"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
          />
          <select
            className="border border-line rounded-md px-2 py-1"
            value={newType}
            onChange={(e) => setNewType(e.target.value as ConnectorType)}
          >
            {(Object.entries(TYPE_LABEL) as [ConnectorType, string][]).map(([v, label]) => (
              <option key={v} value={v}>
                {label}
              </option>
            ))}
          </select>
          <p className="text-xs text-ink-muted">Click on the map to add points ({draftPoints.length} added).</p>
          <div className="flex gap-2 flex-wrap">
            <button className="btn-primary" onClick={saveNew}>
              Save connector
            </button>
            <button className="btn" onClick={() => setDraftPoints(draftPoints.slice(0, -1))}>
              Undo point
            </button>
            <button className="btn" onClick={cancelDrawing}>
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button className="btn-primary self-start" onClick={startDrawingNew}>
          + Add connector
        </button>
      )}
    </div>
  );
}
