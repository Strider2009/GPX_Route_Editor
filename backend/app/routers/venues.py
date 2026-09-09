"""Finding places near a point on a route, and keeping the good ones.

Search results are cached by area so re-opening the panel costs no request.
Anything the user decides - preferred, a note - is theirs and persists; a
preferred venue never needs looking up again.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import history, overpass_fetch
from ..database import get_db
from ..geo import distance_to_route, haversine
from ..models import Day, Poi, Venue, VenueArea
from ..overpass_fetch import KINDS
from ..schemas import PreferredUpdate, VenueToPoiRequest
from ..serializers import day_detail, venue_schema

router = APIRouter(tags=["venues"])

DEFAULT_KINDS = ["cafe", "water", "toilets", "bicycle"]
# Beyond this a search stops being "near the route" and starts hammering Overpass.
MAX_RADIUS_M = 5000


def _get_day_or_404(db: Session, day_id: int) -> Day:
    day = db.get(Day, day_id)
    if not day:
        raise HTTPException(404, "Day not found")
    return day


def _area_key(lat: float, lon: float, radius_m: int, kinds: list[str]) -> str:
    # Rounded to ~11 m so nudging the anchor a metre doesn't force a fresh fetch.
    return f"{lat:.4f},{lon:.4f},{radius_m},{'|'.join(sorted(kinds))}"


def _upsert(db: Session, found: list[dict]) -> list[Venue]:
    """Store what Overpass returned, leaving any user decisions intact."""
    existing = {
        v.external_id: v
        for v in db.query(Venue)
        .filter(Venue.external_id.in_([f["external_id"] for f in found] or [""]))
        .all()
    }
    venues = []
    for f in found:
        venue = existing.get(f["external_id"])
        if venue is None:
            venue = Venue(source="osm", external_id=f["external_id"])
            db.add(venue)
        # Refresh the facts, never the judgement: preferred and user_note are
        # the user's and must survive a re-fetch.
        venue.name = f["name"]
        venue.kind = f["kind"]
        venue.lat = f["lat"]
        venue.lon = f["lon"]
        venue.tags = f["tags"]
        venue.fetched_at = datetime.now(UTC)
        venues.append(venue)
    return venues


@router.get("/days/{day_id}/venues")
def venues_near_point(
    day_id: int,
    point_index: int = Query(..., ge=0, description="Index into the day's points"),
    radius_m: int = Query(1000, ge=50, le=MAX_RADIUS_M),
    kinds: str = Query(",".join(DEFAULT_KINDS), description="Comma-separated kinds"),
    refresh: bool = Query(False, description="Ignore the cached area and re-ask"),
    db: Session = Depends(get_db),
):
    """Places near one point of the route, cached by area."""
    day = _get_day_or_404(db, day_id)
    points = day.points or []
    if point_index >= len(points):
        raise HTTPException(400, f"point_index {point_index} is past the end of the day")

    wanted = [k.strip() for k in kinds.split(",") if k.strip() in KINDS]
    if not wanted:
        raise HTTPException(400, f"kinds must name at least one of {sorted(KINDS)}")

    anchor = points[point_index]
    lat, lon = float(anchor["lat"]), float(anchor["lon"])
    key = _area_key(lat, lon, radius_m, wanted)
    area = db.query(VenueArea).filter(VenueArea.key == key).one_or_none()

    fetched = False
    if area is None or refresh:
        try:
            found = overpass_fetch.search(lat, lon, radius_m, wanted)
        except overpass_fetch.OverpassError as exc:
            raise HTTPException(502, str(exc)) from exc
        _upsert(db, found)
        if area is None:
            area = VenueArea(key=key, lat=lat, lon=lon, radius_m=radius_m, kinds=",".join(wanted))
            db.add(area)
        area.found = len(found)
        area.fetched_at = datetime.now(UTC)
        db.commit()
        fetched = True

    # Read back from the database either way, so a cached answer and a fresh one
    # go through exactly the same path.
    candidates = db.query(Venue).filter(Venue.kind.in_(wanted)).all()
    results = []
    for v in candidates:
        gap = haversine({"lat": lat, "lon": lon}, {"lat": v.lat, "lon": v.lon})
        if gap > radius_m:
            continue
        data = venue_schema(v)
        data["distance_m"] = round(gap, 1)
        # How far off the route it is, which matters more than distance from the
        # anchor when deciding whether a detour is worth it.
        to_route, idx = distance_to_route(v.lat, v.lon, points)
        data["distance_to_route_m"] = round(to_route, 1)
        data["nearest_point_index"] = idx
        results.append(data)

    results.sort(key=lambda r: (not r["preferred"], r["distance_m"]))
    return {
        "day_id": day.id,
        "point_index": point_index,
        "lat": lat,
        "lon": lon,
        "radius_m": radius_m,
        "kinds": wanted,
        "from_cache": not fetched,
        "cached_at": area.fetched_at if area else None,
        "count": len(results),
        "venues": results,
    }


@router.get("/venues/preferred")
def list_preferred(db: Session = Depends(get_db)):
    """Your shortlist, across every trip. Costs nothing and works offline."""
    venues = db.query(Venue).filter(Venue.preferred.is_(True)).order_by(Venue.name).all()
    return [venue_schema(v) for v in venues]


@router.post("/venues/{venue_id}/preferred")
def set_preferred(venue_id: int, payload: PreferredUpdate, db: Session = Depends(get_db)):
    venue = db.get(Venue, venue_id)
    if not venue:
        raise HTTPException(404, "Venue not found")
    venue.preferred = payload.value
    if payload.note is not None:
        venue.user_note = payload.note or None
    db.commit()
    db.refresh(venue)
    return venue_schema(venue)


@router.post("/days/{day_id}/venues/{venue_id}/add")
def add_venue_as_poi(
    day_id: int, venue_id: int, payload: VenueToPoiRequest, db: Session = Depends(get_db)
):
    """Put a found venue onto the route as a POI.

    Only OSM-sourced fields and the user's own note are copied. A ratings
    provider's content must never reach a POI, because POIs are written into
    exported GPX files and that would be storing their content on disk.
    """
    day = _get_day_or_404(db, day_id)
    venue = db.get(Venue, venue_id)
    if not venue:
        raise HTTPException(404, "Venue not found")

    history.record(db, day.project_id, "Add POI from venue")
    poi = Poi(
        day_id=day.id,
        name=(payload.name or venue.name).strip(),
        lat=venue.lat,
        lon=venue.lon,
        symbol=payload.symbol or _default_symbol(venue.kind),
        notes=(payload.notes if payload.notes is not None else venue.user_note),
    )
    db.add(poi)
    db.commit()
    db.refresh(day)
    return day_detail(day)


def _default_symbol(kind: str) -> str | None:
    return {
        "cafe": "Restaurant",
        "food": "Restaurant",
        "water": "Drinking Water",
        "toilets": "Restroom",
        "bicycle": "Bike Trail",
    }.get(kind)
