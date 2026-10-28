import { useEffect, useState } from "react";
import type { DayDetail } from "../api/types";
import { useCompareElevation, useElevationJob, useElevationProviders, useFillElevation } from "../api/hooks";
import ElevationCompare from "./ElevationCompare";

interface Props {
  projectId: number;
  day: DayDetail;
  /** The running or last fill. Held by the page, which outlives this panel when the day changes. */
  fillJobId: string | null;
  setFillJobId: (id: string | null) => void;
}

export default function ElevationPanel({ projectId, day, fillJobId, setFillJobId }: Props) {
  const providers = useElevationProviders();
  const fillElevation = useFillElevation(projectId);
  const job = useElevationJob(projectId, fillJobId).data;
  const running = fillElevation.isPending || job?.status === "running";
  const compareElevation = useCompareElevation();

  const list = providers.data ?? [];
  const [provider, setProvider] = useState<string | null>(null);
  const [overwrite, setOverwrite] = useState(false);
  const [compareWith, setCompareWith] = useState<string[]>([]);
  const [samples, setSamples] = useState(300);
  const [showCompare, setShowCompare] = useState(false);

  // Start from the server's default, and compare against everything on offer.
  useEffect(() => {
    if (list.length === 0) return;
    setProvider((p) => p ?? list.find((x) => x.default)?.id ?? list[0].id);
    setCompareWith((c) => (c.length ? c : list.map((x) => x.id)));
  }, [list]);

  // A comparison describes one day; don't leave it up once another is open.
  useEffect(() => {
    setShowCompare(false);
    compareElevation.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [day.id]);

  const known = day.points.filter((p) => p.ele != null).length;
  const coverage = day.points.length ? known / day.points.length : 0;

  const fill = async () => {
    try {
      setFillJobId((await fillElevation.mutateAsync({ provider, overwrite })).id);
    } catch {
      /* shown below */
    }
  };
  const compare = async () => {
    setShowCompare(true);
    try {
      await compareElevation.mutateAsync({ dayId: day.id, providers: compareWith, samples });
    } catch {
      /* shown in the dialog */
    }
  };

  return (
    <div className="panel">
      <h3 className="panel-title">Elevation data</h3>
      <p className="hint">
        This day has heights for {known.toLocaleString()} of {day.points.length.toLocaleString()} points
        {coverage > 0 && coverage < 1 && ` (${Math.round(coverage * 100)}%)`}. Filling looks them up from
        a terrain model for every day in the trip, and can be undone.
      </p>

      <label className="text-xs flex items-center justify-between gap-2">
        Source
        <select
          className="border border-line rounded-md px-1 py-0.5 max-w-[11rem]"
          value={provider ?? ""}
          onChange={(e) => setProvider(e.target.value)}
        >
          {list.map((p) => (
            <option key={p.id} value={p.id} title={p.description}>
              {p.label}
            </option>
          ))}
        </select>
      </label>
      <label className="text-xs flex items-center gap-2">
        <input type="checkbox" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} />
        Replace heights the route already has
      </label>
      <button className="btn-teal" disabled={!provider || running} onClick={fill}>
        {running ? "Looking up heights..." : overwrite ? "Replace elevation" : "Fill missing elevation"}
      </button>
      {fillElevation.isError && <p className="text-red-600 text-xs">{(fillElevation.error as Error).message}</p>}
      {job?.status === "running" && (
        <div className="flex flex-col gap-1">
          <div
            className="h-1.5 rounded-full bg-line overflow-hidden"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={job.total}
            aria-valuenow={job.done}
          >
            <div
              className="h-full bg-teal transition-[width]"
              style={{ width: `${job.total ? (job.done / job.total) * 100 : 0}%` }}
            />
          </div>
          <p className="hint">
            {job.provider_label}: {job.done.toLocaleString()} of {job.total.toLocaleString()} locations.
            Rate-limited sources pace themselves, so a long trip can take a few minutes - you can keep
            working meanwhile.
          </p>
        </div>
      )}
      {job?.status === "error" && <p className="text-red-600 text-xs">{job.error}</p>}
      {job?.status === "done" && (
        <p className="text-xs text-ink-muted">
          {job.filled
            ? `${job.provider_label} set heights on ${job.filled.toLocaleString()} points.`
            : "Nothing to fill - every point already has a height."}
        </p>
      )}

      <div className="border-t border-line pt-2 mt-1 flex flex-col gap-1">
        <span className="text-xs font-medium">Compare sources on this day</span>
        <p className="hint">
          {known
            ? "Scores each source against the heights the route already has. Nothing is changed."
            : "This day has no heights of its own, so sources can only be compared with each other."}
        </p>
        {list.map((p) => (
          <label key={p.id} className="text-xs flex items-center gap-2" title={p.description}>
            <input
              type="checkbox"
              checked={compareWith.includes(p.id)}
              onChange={(e) =>
                setCompareWith((c) => (e.target.checked ? [...c, p.id] : c.filter((x) => x !== p.id)))
              }
            />
            {p.label}
          </label>
        ))}
        <label className="text-xs flex items-center justify-between gap-2">
          Sample points
          <input
            type="number"
            min={10}
            max={1000}
            step={50}
            className="border border-line rounded-md px-1 py-0.5 w-20"
            value={samples}
            onChange={(e) => setSamples(Number(e.target.value))}
          />
        </label>
        <button className="btn" disabled={compareWith.length === 0 || compareElevation.isPending} onClick={compare}>
          {compareElevation.isPending ? "Comparing..." : "Compare sources"}
        </button>
      </div>

      {showCompare && (
        <ElevationCompare
          providerOrder={list.map((p) => p.id)}
          pending={compareElevation.isPending}
          error={compareElevation.isError ? (compareElevation.error as Error).message : null}
          result={compareElevation.data ?? null}
          onClose={() => setShowCompare(false)}
        />
      )}
    </div>
  );
}
