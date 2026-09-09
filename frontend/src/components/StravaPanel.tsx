import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  useDisconnectStrava,
  useImportStravaRoute,
  useStravaRoutes,
  useStravaStatus,
} from "../api/hooks";

const METRES_PER_MILE = 1609.344;

export default function StravaPanel() {
  const navigate = useNavigate();
  const status = useStravaStatus();
  const [browsing, setBrowsing] = useState(false);
  const routes = useStravaRoutes(browsing && !!status.data?.connected);
  const importRoute = useImportStravaRoute();
  const disconnect = useDisconnectStrava();

  if (status.isLoading || !status.data) return null;

  if (!status.data.configured) {
    return (
      <section className="panel shadow-card gap-3">
        <h2 className="text-xl font-bold text-brand">Strava</h2>
        <p className="text-sm text-ink-muted">
          Not configured. Create an app at{" "}
          <a
            className="text-brand hover:underline"
            href="https://www.strava.com/settings/api"
            target="_blank"
            rel="noreferrer"
          >
            strava.com/settings/api
          </a>{" "}
          using these values:
        </p>
        <table className="text-sm border border-line rounded-md overflow-hidden">
          <tbody>
            <tr className="border-b border-line">
              <td className="px-2 py-1 bg-page font-medium align-top">Website</td>
              <td className="px-2 py-1">
                <code>http://localhost:8090</code>
                <div className="text-xs text-ink-muted">Not checked - anything valid works.</div>
              </td>
            </tr>
            <tr>
              <td className="px-2 py-1 bg-page font-medium align-top">
                Authorization
                <br />
                Callback Domain
              </td>
              <td className="px-2 py-1">
                <code>localhost</code>
                <div className="text-xs text-ink-muted">
                  Bare domain only - no <code>http://</code>, no port, no path. The port is ignored,
                  so this covers <code>{status.data.redirect_uri}</code>.
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        <p className="text-sm text-ink-muted">
          Then put the Client ID and Secret in a <code>.env</code> next to{" "}
          <code>docker-compose.yml</code> as <code>STRAVA_CLIENT_ID</code> and{" "}
          <code>STRAVA_CLIENT_SECRET</code>, and run <code>docker compose up -d</code>.
        </p>
      </section>
    );
  }

  if (!status.data.connected) {
    return (
      <section className="panel shadow-card">
        <h2 className="text-xl font-bold text-brand">Strava</h2>
        <p className="text-sm text-ink-muted">Connect your account to import routes directly.</p>
        <a className="btn-primary self-start" href="/api/strava/connect">
          Connect Strava
        </a>
      </section>
    );
  }

  return (
    <section className="panel shadow-card">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-semibold">
          Strava{status.data.athlete_name ? ` · ${status.data.athlete_name}` : ""}
        </h2>
        <div className="flex gap-2">
          <button className="btn" onClick={() => setBrowsing((b) => !b)}>
            {browsing ? "Hide routes" : "Browse my routes"}
          </button>
          <button
            className="btn-danger"
            onClick={() => {
              if (confirm("Disconnect Strava?")) disconnect.mutate();
            }}
          >
            Disconnect
          </button>
        </div>
      </div>

      {browsing && (
        <>
          {routes.isLoading && <p className="text-sm text-ink-muted">Loading routes...</p>}
          {routes.isError && <p className="text-sm text-red-600">{(routes.error as Error).message}</p>}
          {importRoute.isError && (
            <p className="text-sm text-red-600">{(importRoute.error as Error).message}</p>
          )}
          <ul className="flex flex-col gap-1 max-h-96 overflow-y-auto">
            {routes.data?.map((r) => (
              <li key={r.id_str} className="border border-line rounded-md px-3 py-2 flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <div className="font-medium truncate">{r.name}</div>
                  <div className="text-xs text-ink-muted">
                    {(r.distance_m / METRES_PER_MILE).toFixed(1)} mi
                    {r.elevation_gain_m ? ` · ${Math.round(r.elevation_gain_m)} m climb` : ""}
                    {r.private ? " · private" : ""}
                    {r.starred ? " · starred" : ""}
                  </div>
                </div>
                <button
                  className="btn-primary shrink-0"
                  disabled={importRoute.isPending}
                  onClick={() =>
                    importRoute.mutate(
                      { routeId: r.id_str },
                      { onSuccess: (project) => navigate(`/projects/${project.id}`) }
                    )
                  }
                >
                  {importRoute.isPending ? "Importing..." : "Import"}
                </button>
              </li>
            ))}
            {routes.data?.length === 0 && (
              <li className="text-sm text-ink-muted">No routes found on this account.</li>
            )}
          </ul>
        </>
      )}
    </section>
  );
}
