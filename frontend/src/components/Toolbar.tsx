import { Link } from "react-router-dom";
import type { ProjectDetail } from "../api/types";
import { api } from "../api/client";
import { useEffect } from "react";
import { useAddRoutesToProject, useHistory, useRedo, useUndo } from "../api/hooks";

interface Props {
  project: ProjectDetail;
  selectedDayId: number | null;
}

export default function Toolbar({ project, selectedDayId }: Props) {
  const addRoutes = useAddRoutesToProject(project.id);
  const history = useHistory(project.id);
  const undo = useUndo(project.id);
  const redo = useRedo(project.id);
  const busy = undo.isPending || redo.isPending;

  // Ctrl/Cmd+Z and Ctrl/Cmd+Shift+Z, skipped while typing in a field.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== "z") return;
      const el = document.activeElement;
      if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) return;
      e.preventDefault();
      if (e.shiftKey) redo.mutate();
      else undo.mutate();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [undo, redo]);

  return (
    <header className="navbar flex items-center justify-between gap-4 flex-wrap px-4 py-2.5">
      <div className="flex items-center gap-3 min-w-0">
        <Link to="/" className="nav-link shrink-0">
          &larr; Projects
        </Link>
        <span className="h-5 w-px bg-white/20 shrink-0" aria-hidden />
        <h1 className="font-medium truncate text-white">{project.name}</h1>
      </div>
      <div className="flex items-center gap-2 text-sm flex-wrap">
        <div className="flex items-center gap-1">
          <button
            className="btn-bar"
            disabled={!history.data?.can_undo || busy}
            title={history.data?.undo_action ? `Undo ${history.data.undo_action}` : "Nothing to undo"}
            onClick={() => undo.mutate()}
          >
            ↶ Undo
          </button>
          <button
            className="btn-bar"
            disabled={!history.data?.can_redo || busy}
            title={history.data?.redo_action ? `Redo ${history.data.redo_action}` : "Nothing to redo"}
            onClick={() => redo.mutate()}
          >
            ↷ Redo
          </button>
          {history.data?.undo_action && (
            <span className="text-xs text-white/45 hidden lg:inline">
              {history.data.undo_action}
            </span>
          )}
        </div>

        <label className="btn-primary cursor-pointer">
          {addRoutes.isPending ? "Adding..." : "+ Add routes"}
          <input
            type="file"
            accept=".gpx"
            multiple
            className="hidden"
            onChange={(e) => {
              const files = Array.from(e.target.files ?? []);
              if (files.length) addRoutes.mutate(files);
              e.target.value = "";
            }}
          />
        </label>
        {addRoutes.isError && (
          <span className="text-red-300 text-xs">{(addRoutes.error as Error).message}</span>
        )}
        {selectedDayId != null && (
          <a className="btn-bar" href={api.exportDayUrl(selectedDayId)} target="_blank" rel="noreferrer">
            Export selected day
          </a>
        )}
        <a className="btn-bar" href={api.exportProjectUrl(project.id, "combined")} target="_blank" rel="noreferrer">
          Export trip (combined)
        </a>
        <a className="btn-bar" href={api.exportProjectUrl(project.id, "zip")} target="_blank" rel="noreferrer">
          Export trip (zip per day)
        </a>
      </div>
    </header>
  );
}
