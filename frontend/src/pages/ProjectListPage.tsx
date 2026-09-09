import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useDeleteProject, useImportProject, useProjects } from "../api/hooks";
import StravaPanel from "../components/StravaPanel";

export default function ProjectListPage() {
  const { data: projects, isLoading } = useProjects();
  const importProject = useImportProject();
  const deleteProject = useDeleteProject();
  const navigate = useNavigate();

  const [files, setFiles] = useState<File[]>([]);
  const [name, setName] = useState("");

  const handleImport = () => {
    if (files.length === 0) return;
    importProject.mutate(
      { files, name: name || undefined },
      { onSuccess: (project) => navigate(`/projects/${project.id}`) }
    );
  };

  return (
    <div className="min-h-full bg-page">
      <header className="navbar">
        <div className="max-w-3xl mx-auto px-6 h-14 flex items-center">
          <span className="font-medium text-white">GPX Route Editor</span>
        </div>
      </header>

      <div className="banner">
        <div className="max-w-3xl mx-auto px-6 py-12">
          <h1 className="text-4xl font-bold tracking-tight">Your routes</h1>
          <p className="mt-2 text-white/80">Plan and reshape multi-day cycling tours</p>
        </div>
      </div>

      <div className="max-w-3xl mx-auto p-6 flex flex-col gap-4 -mt-6">
        <StravaPanel />

        <section className="panel gap-3 shadow-card">
          <h2 className="text-xl font-bold text-brand">Import a GPX route</h2>
          <input
            type="file"
            accept=".gpx"
            multiple
            className="text-sm file:mr-3 file:rounded-md file:border-0 file:bg-brand file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-white hover:file:bg-brand-dark file:cursor-pointer"
            onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
          />
          <input
            type="text"
            placeholder="Project name (optional)"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <button
            className="btn-primary self-start"
            disabled={files.length === 0 || importProject.isPending}
            onClick={handleImport}
          >
            {importProject.isPending ? "Importing..." : "Import"}
          </button>
          {importProject.isError && (
            <p className="text-red-600 text-sm">{(importProject.error as Error).message}</p>
          )}
          <p className="hint">
            Multiple files, or a single file with several tracks, will each become a separate day
            that you can reorder, split or merge afterwards.
          </p>
        </section>

        <section className="flex flex-col gap-2 mt-2">
          <h2 className="text-xl font-bold text-brand px-1">Your projects</h2>
          {isLoading && <p className="text-sm text-ink-muted px-1">Loading...</p>}
          <ul className="flex flex-col gap-2">
            {projects?.map((p) => (
              <li
                key={p.id}
                className="group bg-surface border border-line rounded-lg shadow-card hover:border-brand transition-colors flex items-center justify-between gap-2"
              >
                <button
                  className="text-left min-w-0 flex-1 px-4 py-3"
                  onClick={() => navigate(`/projects/${p.id}`)}
                >
                  <div className="font-medium truncate group-hover:text-brand transition-colors">
                    {p.name}
                  </div>
                  <div className="text-xs text-ink-muted mt-0.5">
                    {p.day_count} day{p.day_count === 1 ? "" : "s"} &middot; imported{" "}
                    {new Date(p.created_at).toLocaleDateString()}
                  </div>
                </button>
                <button
                  className="btn-danger shrink-0 mr-3"
                  onClick={() => {
                    if (confirm(`Delete project "${p.name}"?`)) deleteProject.mutate(p.id);
                  }}
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
          {projects?.length === 0 && (
            <p className="text-sm text-ink-muted border border-dashed border-line rounded-lg p-6 text-center">
              No projects yet - import a GPX file above.
            </p>
          )}
        </section>
      </div>
    </div>
  );
}
