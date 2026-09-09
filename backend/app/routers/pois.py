from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import history
from ..database import get_db
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
