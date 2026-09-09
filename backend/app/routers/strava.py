import os
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .. import strava
from ..database import get_db
from ..gpx_io import parse_gpx
from ..models import Day, Project, StravaAuth
from ..route_ops import detect_circular
from ..serializers import project_detail

router = APIRouter(tags=["strava"])

APP_URL = os.environ.get("APP_URL", "http://localhost:8090")


def _current(db: Session) -> StravaAuth | None:
    return db.query(StravaAuth).order_by(StravaAuth.id.desc()).first()


def _bootstrap_from_env(db: Session) -> StravaAuth | None:
    """Seed the connection from STRAVA_REFRESH_TOKEN, skipping the browser flow.

    Access tokens last about six hours; the refresh token is the durable part, so
    one is enough to get going and keep going.
    """
    seed = os.environ.get("STRAVA_REFRESH_TOKEN", "").strip()
    if not seed:
        return None
    try:
        payload = strava.refresh(seed)
    except (strava.StravaNotConfigured, strava.StravaError) as exc:
        raise HTTPException(502, f"STRAVA_REFRESH_TOKEN could not be exchanged: {exc}") from exc

    auth = StravaAuth(
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token", seed),
        expires_at=strava.expiry_from(payload),
        scope="(from STRAVA_REFRESH_TOKEN)",
    )
    db.add(auth)
    db.commit()

    try:
        info = strava.athlete(auth.access_token)
        auth.athlete_id = info.get("id")
        auth.athlete_name = (
            " ".join(filter(None, [info.get("firstname"), info.get("lastname")])).strip() or None
        )
        db.commit()
    except strava.StravaError:
        pass  # the token works even if the profile lookup doesn't

    return auth


def _valid_token(db: Session) -> str:
    """Return a usable access token, refreshing it if it's close to expiry."""
    auth = _current(db) or _bootstrap_from_env(db)
    if not auth:
        raise HTTPException(401, "Strava is not connected")

    now = datetime.now(UTC).replace(tzinfo=None)
    if auth.expires_at - now > timedelta(minutes=5):
        return auth.access_token

    try:
        payload = strava.refresh(auth.refresh_token)
    except strava.StravaNotConfigured as exc:
        raise HTTPException(503, str(exc)) from exc
    except strava.StravaError as exc:
        raise HTTPException(502, f"Could not refresh the Strava token: {exc}") from exc

    auth.access_token = payload["access_token"]
    auth.refresh_token = payload.get("refresh_token", auth.refresh_token)
    auth.expires_at = strava.expiry_from(payload)
    db.commit()
    return auth.access_token


@router.get("/strava/status")
def status(db: Session = Depends(get_db)):
    auth = _current(db)
    has_seed = bool(os.environ.get("STRAVA_REFRESH_TOKEN", "").strip())
    return {
        "configured": strava.is_configured(),
        "connected": auth is not None or has_seed,
        "athlete_name": auth.athlete_name if auth else None,
        "athlete_id": auth.athlete_id if auth else None,
        "expires_at": auth.expires_at.isoformat() if auth else None,
        "scope": auth.scope if auth else None,
        "redirect_uri": strava.redirect_uri(),
    }


@router.get("/strava/connect")
def connect():
    """Send the browser to Strava's consent screen."""
    try:
        return RedirectResponse(strava.authorize_url())
    except strava.StravaNotConfigured as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/strava/callback")
def callback(
    code: str | None = Query(None),
    error: str | None = Query(None),
    scope: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Strava redirects here after consent; swap the code for tokens."""
    if error:
        return RedirectResponse(f"{APP_URL}/?strava_error={error}")
    if not code:
        return RedirectResponse(f"{APP_URL}/?strava_error=missing_code")

    try:
        payload = strava.exchange_code(code)
    except (strava.StravaNotConfigured, strava.StravaError) as exc:
        return RedirectResponse(f"{APP_URL}/?strava_error={type(exc).__name__}")

    info = payload.get("athlete") or {}
    name = " ".join(filter(None, [info.get("firstname"), info.get("lastname")])).strip() or None

    auth = _current(db) or StravaAuth()
    auth.athlete_id = info.get("id")
    auth.athlete_name = name
    auth.access_token = payload["access_token"]
    auth.refresh_token = payload["refresh_token"]
    auth.expires_at = strava.expiry_from(payload)
    auth.scope = scope
    if auth.id is None:
        db.add(auth)
    db.commit()

    return RedirectResponse(f"{APP_URL}/?strava=connected")


@router.post("/strava/disconnect", status_code=204)
def disconnect(db: Session = Depends(get_db)):
    auth = _current(db)
    if auth:
        db.delete(auth)
        db.commit()


@router.get("/strava/routes")
def list_routes(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    token = _valid_token(db)
    try:
        routes = strava.list_routes(token, page=page, per_page=per_page)
    except strava.StravaError as exc:
        raise HTTPException(502, str(exc)) from exc

    return [
        {
            "id": r.get("id"),
            "id_str": str(r.get("id")),
            "name": r.get("name"),
            "description": r.get("description"),
            "distance_m": r.get("distance"),
            "elevation_gain_m": r.get("elevation_gain"),
            "type": r.get("type"),
            "sub_type": r.get("sub_type"),
            "private": r.get("private"),
            "starred": r.get("starred"),
            "created_at": r.get("created_at"),
            "estimated_moving_time_s": r.get("estimated_moving_time"),
        }
        for r in routes
    ]


@router.post("/strava/routes/{route_id}/import")
def import_route(route_id: int, name: str | None = Query(None), db: Session = Depends(get_db)):
    """Pull a route's GPX from Strava and turn it into a project."""
    token = _valid_token(db)
    try:
        data = strava.export_route_gpx(token, route_id)
    except strava.StravaError as exc:
        raise HTTPException(502, str(exc)) from exc

    try:
        tracks = parse_gpx(data)
    except Exception as exc:
        raise HTTPException(
            400, f"Strava returned something we couldn't parse as GPX: {exc}"
        ) from exc

    project = Project(name=name or tracks[0]["name"], source_filename=f"strava:{route_id}")
    db.add(project)
    db.flush()

    for order, track in enumerate(tracks):
        db.add(
            Day(
                project_id=project.id,
                name=track["name"],
                order_index=order,
                is_circular=detect_circular(track["points"]),
                is_locked=False,
                points=track["points"],
                source_points=list(track["points"]),
            )
        )

    db.commit()
    db.refresh(project)
    return project_detail(project)
