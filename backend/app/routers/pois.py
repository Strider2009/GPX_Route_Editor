from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import history, overpass_fetch, poi_describe
from ..briefing import _places_cached
from ..database import get_db
from ..geo import haversine
from ..models import Day, Poi
from ..schemas import PoiCreate, PoiUpdate
from ..serializers import day_detail, poi_schema

router = APIRouter(tags=["pois"])


def get_day_or_404(db: Session, day_id: int) -> Day:
    day = db.get(Day, day_id)
    if not day:
        raise HTTPException(404, "Day not found")
    return day


def get_poi_or_404(db: Session, poi_id: int) -> Poi:
    poi = db.get(Poi, poi_id)
    if not poi:
        raise HTTPException(404, "POI not found")
    return poi


@router.post("/days/{day_id}/pois")
def add_poi(day_id: int, payload: PoiCreate, db: Session = Depends(get_db)):
    # Deliberately no is_locked check: a POI is a marker beside the route, not a
    # change to it, so locking a day still lets you mark a cafe on it.
    day = get_day_or_404(db, day_id)
    history.record(db, day.project_id, "Add POI")
    poi = Poi(
        day_id=day.id,
        name=payload.name,
        lat=payload.lat,
        lon=payload.lon,
        ele=payload.ele,
        symbol=payload.symbol,
        notes=payload.notes,
    )
    db.add(poi)
    db.commit()
    db.refresh(day)
    return day_detail(day)


@router.put("/pois/{poi_id}")
def update_poi(poi_id: int, payload: PoiUpdate, db: Session = Depends(get_db)):
    poi = get_poi_or_404(db, poi_id)
    history.record(db, poi.day.project_id, "Edit POI")
    for field in ("name", "lat", "lon", "ele", "symbol", "notes"):
        value = getattr(payload, field)
        if value is not None:
            # An empty symbol or note is how the panel clears one; store no value
            # rather than writing empty <sym>/<desc> tags into exports.
            if field in ("symbol", "notes") and not value.strip():
                value = None
            setattr(poi, field, value)
    db.commit()
    db.refresh(poi)
    return poi_schema(poi)


@router.delete("/pois/{poi_id}", status_code=204)
def delete_poi(poi_id: int, db: Session = Depends(get_db)):
    poi = get_poi_or_404(db, poi_id)
    history.record(db, poi.day.project_id, "Delete POI")
    db.delete(poi)
    db.commit()


@router.post("/days/{day_id}/pois/describe")
def describe_pois(day_id: int, db: Session = Depends(get_db)):
    """Name and annotate the day's waypoints from where they actually are.

    Only fills what nobody wrote: a generic name like "Waypoint" is replaced and
    empty notes are filled, but anything a person typed is left alone. So it is
    safe to run again after adding more markers.
    """
    day = get_day_or_404(db, day_id)
    todo = [p for p in day.pois if poi_describe.is_generic(p.name) or not p.notes]
    if not todo:
        return {"updated": 0, "places_error": None, "day": day_detail(day)}

    as_dicts = [{"lat": p.lat, "lon": p.lon, "name": p.name, "ele": p.ele} for p in todo]
    try:
        elements = poi_describe.fetch(as_dicts)
    except overpass_fetch.OverpassError as exc:
        # Nothing is changed, so the user can simply retry.
        raise HTTPException(503, str(exc)) from exc

    points = day.points or []
    places: list[dict] = []
    places_error = None
    if points:
        try:
            # The waypoints go into the search area too: one well off the route
            # still deserves the name of the village it is actually in.
            area = points + [{"lat": d["lat"], "lon": d["lon"]} for d in as_dicts]
            places = _places_cached(db, area, 2000, refresh=False)
        except overpass_fetch.OverpassError as exc:
            # Roads and landmarks are already in hand; the town name is a bonus.
            places_error = str(exc)

    cumulative = [0.0]
    for a, b in zip(points, points[1:], strict=False):
        cumulative.append(cumulative[-1] + haversine(a, b))

    history.record(db, day.project_id, "Describe POIs")
    for poi, d in zip(todo, as_dicts, strict=True):
        found = poi_describe.describe(d, points, cumulative, elements, places)
        if poi_describe.is_generic(poi.name):
            poi.name = found["name"]
        if not poi.notes:
            poi.notes = found["notes"]
        if poi.ele is None:
            poi.ele = found["ele"]
    db.commit()
    db.refresh(day)
    return {"updated": len(todo), "places_error": places_error, "day": day_detail(day)}
