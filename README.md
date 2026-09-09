# GPX Route Editor

A self-hosted tool for reshaping GPX routes for trip planning: mark loops as circular and
pick a new start/end point, split a big route into per-day sections, lock a day's core route
so later additions (like a spur to a hotel or cafe) can't accidentally change it, and view/edit
everything on a map and in a point list.

## Running it

Requires Docker and Docker Compose.

```bash
docker compose up --build
```

Then open [http://localhost:8090](http://localhost:8090). The backend API is also reachable
directly at [http://localhost:8000](http://localhost:8000) (interactive docs at `/docs`).

All data (the SQLite database) is stored in `./data`, which is bind-mounted into the backend
container, so it survives container restarts/rebuilds.

## Local development (without Docker)

Backend:

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate  # or `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api` to `http://localhost:8000` (see `frontend/vite.config.ts`),
so run the backend alongside it.

## Connecting Strava (optional)

Lets you browse and import your Strava routes directly instead of exporting GPX by hand.
Strava requires an active subscription for API access.

1. Go to [strava.com/settings/api](https://www.strava.com/settings/api) and create an
   application:

   | Field | Value |
   | --- | --- |
   | Website | `http://localhost:8090` (not validated - any valid URL is fine) |
   | Authorization Callback Domain | `localhost` |

   The callback domain must be the **bare domain**: no `http://`, no port, no path. Pasting the
   full callback URL there is the usual reason authorisation fails. The port isn't part of the
   check, so `localhost` covers `http://localhost:8090/api/strava/callback`.
2. Put the Client ID and Client Secret in a `.env` file next to `docker-compose.yml`:

   ```
   STRAVA_CLIENT_ID=your_client_id
   STRAVA_CLIENT_SECRET=your_client_secret
   ```

3. `docker compose up -d --build`, then click **Connect Strava** on the home page.

The client secret stays in the environment; only the access and refresh tokens are stored in
the database, and the access token is refreshed automatically when it expires.

Garmin and komoot are not supported: Garmin's Connect Developer Program is business-only with
no hobbyist tier, and komoot has no public API (partner agreements only).

## How it works

- **Import**: upload one or more `.gpx` files. Each `<trk>` (or `<rte>` if there are no tracks)
  in a file becomes its own "day". A day whose start and end are close together is automatically
  suggested as circular.
- **Circular routes**: toggle "Circular route (loop)" for a day, select a point on the map or in
  the list, then "Set selected point as start/end" to rotate the loop to start there.
- **Point-to-point routes**: mark a range start and end point, then "Trim route to selection" to
  cut the route down, or "Reverse direction" to flip it.
- **Splitting into days**: select a point and "Split into two days here" to break one day into
  two, each independently editable. Days can be reordered, renamed, or deleted from the sidebar.
- **Locking**: toggle "Lock core route" on a day to prevent any further edits to its route
  geometry (rotate/trim/reverse/split all become blocked with a clear error). Locking never
  affects connectors.
- **Connectors**: add a named "start access", "end access", or "spur" leg to a day by drawing
  points on the map - useful for a walk from the route to a hotel or cafe. Connectors are
  completely independent of the day's lock.
- **Export**: download a single day (optionally including its connectors), the whole trip as one
  combined GPX file, or the whole trip as a zip of per-day GPX files.

## Project layout

```
backend/    FastAPI + SQLAlchemy + gpxpy application (Python)
frontend/   React + TypeScript + Vite application, Leaflet map, Tailwind styling
data/       SQLite database (created on first run, gitignored)
```
