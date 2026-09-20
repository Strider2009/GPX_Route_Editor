import { useEffect, useState } from "react";
import type { DayDetail } from "../api/types";
import {
  useBriefing,
  useBriefingCacheStatus,
  useBriefingNarrative,
  useClearBriefingCache,
  useRefreshBriefingFacts,
} from "../api/hooks";

interface Props {
  day: DayDetail;
}

const CATEGORY_LABEL: Record<string, string> = {
  HC: "hors catégorie",
  "1": "cat 1",
  "2": "cat 2",
  "3": "cat 3",
  "4": "cat 4",
};

/** The briefing is document-shaped, so it gets a dialog rather than a 320px column. */
export default function BriefingPanel({ day }: Props) {
  const [open, setOpen] = useState(false);
  const briefing = useBriefing(day.id, open);
  const narrative = useBriefingNarrative(day.id);
  const refreshFacts = useRefreshBriefingFacts(day.id);
  const cache = useBriefingCacheStatus(open);
  const clearCache = useClearBriefingCache();

  // A different day means a different briefing; don't leave the old one up.
  useEffect(() => {
    setOpen(false);
    narrative.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [day.id]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const facts = briefing.data;

  return (
    <div className="panel">
      <h3 className="panel-title">Rider briefing</h3>
      <p className="text-xs text-ink-muted">
        Distance, climbs and the places you pass, worked out from the route itself.
      </p>
      <button className="btn-primary self-start" onClick={() => setOpen(true)}>
        Show briefing
      </button>

      {open && (
        <>
          <div
            className="fixed inset-0 z-[1900] bg-black/40"
            onClick={() => setOpen(false)}
            aria-hidden
          />
          <div
            role="dialog"
            aria-label={`Rider briefing for ${day.name}`}
            className="fixed z-[2000] inset-x-0 top-10 mx-auto w-[min(46rem,92vw)] max-h-[82vh] overflow-y-auto
                       bg-surface border border-line rounded-lg shadow-lg p-4 flex flex-col gap-3"
          >
            <div className="flex items-start justify-between gap-3">
              <h2 className="text-lg font-semibold">{day.name}</h2>
              <div className="flex gap-2 shrink-0">
                <button
                  className="btn"
                  onClick={() => {
                    narrative.reset();
                    refreshFacts.mutate();
                  }}
                  disabled={refreshFacts.isPending}
                  title="Re-ask OpenStreetMap for the places on this route"
                >
                  {refreshFacts.isPending ? "Refreshing..." : "Refresh places"}
                </button>
                <button className="btn" onClick={() => setOpen(false)}>
                  Close
                </button>
              </div>
            </div>

            {briefing.isLoading && <p className="text-sm text-ink-muted">Working it out...</p>}
            {briefing.error && (
              <p className="text-sm text-red-600">{(briefing.error as Error).message}</p>
            )}

            {facts && (
              <>
                <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
                  <span>
                    <strong>{facts.distance_km}</strong> km
                  </span>
                  <span>
                    <strong>{facts.ascent_m}</strong> m up
                  </span>
                  <span>
                    <strong>{facts.descent_m}</strong> m down
                  </span>
                  {facts.profile.has_elevation && (
                    <span className="text-ink-muted">
                      {facts.profile.min_ele_m}-{facts.profile.max_ele_m} m altitude
                    </span>
                  )}
                  <span className="text-ink-muted">
                    {facts.is_circular ? "loop" : "point to point"}
                  </span>
                </div>

                <section>
                  <h4 className="font-medium text-sm mb-1">
                    Climbs {facts.climbs.length > 0 && `(${facts.climbs.length})`}
                  </h4>
                  {facts.climbs.length === 0 ? (
                    <p className="text-sm text-ink-muted">No sustained climbs.</p>
                  ) : (
                    <ul className="flex flex-col gap-1">
                      {facts.climbs.map((c) => (
                        <li key={c.start_index} className="text-sm flex flex-wrap gap-x-3">
                          <span className="text-ink-muted w-16 shrink-0">{c.at_km} km</span>
                          <span>
                            <strong>{(c.length_m / 1000).toFixed(1)} km</strong> at{" "}
                            <strong>{c.avg_gradient}%</strong>
                          </span>
                          <span className="text-ink-muted">
                            +{Math.round(c.gain_m)} m, steepest {c.max_gradient}%
                          </span>
                          {c.category && (
                            <span className="text-xs rounded px-1 bg-amber-100 text-amber-800">
                              {CATEGORY_LABEL[c.category] ?? c.category}
                            </span>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </section>

                <section>
                  <h4 className="font-medium text-sm mb-1">Places you pass</h4>
                  {facts.places_error ? (
                    <p className="text-sm text-amber-700">
                      Place names unavailable: {facts.places_error}
                    </p>
                  ) : facts.places.length === 0 ? (
                    <p className="text-sm text-ink-muted">No named settlements near the route.</p>
                  ) : (
                    <ul className="flex flex-col gap-0.5">
                      {facts.places.map((p) => (
                        <li key={`${p.name}-${p.at_index}`} className="text-sm flex gap-3">
                          <span className="text-ink-muted w-16 shrink-0">{p.at_km} km</span>
                          <span>{p.name}</span>
                          <span className="text-ink-muted">
                            {p.place} · {Math.round(p.distance_m)} m off route
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>

                {facts.pois.length > 0 && (
                  <section>
                    <h4 className="font-medium text-sm mb-1">Marked stops</h4>
                    <ul className="flex flex-col gap-0.5">
                      {facts.pois.map((p) => (
                        <li key={p.name} className="text-sm">
                          {p.name}
                          {p.notes && <span className="text-ink-muted"> — {p.notes}</span>}
                        </li>
                      ))}
                    </ul>
                  </section>
                )}

                <section className="border-t border-line pt-3">
                  {narrative.data ? (
                    <div className="flex flex-col gap-2">
                      {narrative.data.briefing.split("\n\n").map((para, i) => (
                        <p key={i} className="text-sm leading-relaxed">
                          {para}
                        </p>
                      ))}
                      <div className="flex gap-2 items-center flex-wrap">
                        <button
                          className="btn"
                          onClick={() => narrative.mutate({ refresh: true })}
                          disabled={narrative.isPending}
                          title="Ignore the cached text and write a new one"
                        >
                          {narrative.isPending ? "Rewriting..." : "Rewrite"}
                        </button>
                        <span className="text-xs text-ink-muted">
                          Re-opening is free; rewriting costs a model call.
                        </span>
                      </div>
                    </div>
                  ) : (
                    <div className="flex flex-col gap-1 items-start">
                      <button
                        className="btn-primary"
                        onClick={() => narrative.mutate({})}
                        disabled={narrative.isPending}
                      >
                        {narrative.isPending ? "Writing..." : "Write it up"}
                      </button>
                      {narrative.error && (
                        <p className="text-xs text-amber-700">
                          {(narrative.error as Error).message}
                        </p>
                      )}
                      <p className="text-xs text-ink-muted">
                        Turns the facts above into prose. Needs ANTHROPIC_API_KEY and costs one
                        model call.
                      </p>
                    </div>
                  )}

                  {cache.data && (
                    <div className="flex items-center gap-2 flex-wrap mt-3 pt-2 border-t border-line">
                      <span className="text-xs text-ink-muted">
                        Cached: {cache.data.narratives} briefing
                        {cache.data.narratives === 1 ? "" : "s"}, {cache.data.place_lookups} place
                        lookup{cache.data.place_lookups === 1 ? "" : "s"}
                      </span>
                      <button
                        className="btn-danger"
                        onClick={() => {
                          narrative.reset();
                          clearCache.mutate({});
                        }}
                        disabled={clearCache.isPending}
                        title="Throw away every cached briefing and place lookup"
                      >
                        {clearCache.isPending ? "Clearing..." : "Clear cache"}
                      </button>
                    </div>
                  )}
                </section>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}
