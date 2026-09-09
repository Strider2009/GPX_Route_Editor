from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import history, route_ops, weather
from ..database import get_db
from ..geo import cumulative_distance, haversine
from ..gpx_io import build_gpx, day_export_segments
from ..models import Day
from ..schemas import BoolValue, DayUpdate, MergeRequest, RotateRequest, SplitRequest, TrimRequest
from ..serializers import day_detail
from ..util import slugify

router = APIRouter(tags=["days"])


def get_day_or_404(db: Session, day_id: int) -> Day:
    day = db.get(Day, day_id)
    if not day:
        raise HTTPException(404, "Day not found")
    return day


@router.get("/days/{day_id}")
def get_day(day_id: int, db: Session = Depends(get_db)):
    return day_detail(get_day_or_404(db, day_id))


@router.patch("/days/{day_id}")
def update_day(day_id: int, payload: DayUpdate, db: Session = Depends(get_db)):
    day = get_day_or_404(db, day_id)
    history.record(db, day.project_id, "Rename day")
    if payload.name is not None:
        day.name = payload.name
    if payload.order_index is not None:
        day.order_index = payload.order_index
    db.commit()
    db.refresh(day)
    return day_detail(day)


@router.delete("/days/{day_id}", status_code=204)
def delete_day(day_id: int, db: Session = Depends(get_db)):
    day = get_day_or_404(db, day_id)
    history.record(db, day.project_id, "Delete day")
    db.delete(day)
    db.commit()


@router.post("/days/{day_id}/circular")
def set_circular(day_id: int, payload: BoolValue, db: Session = Depends(get_db)):
    day = get_day_or_404(db, day_id)
    history.record(db, day.project_id, "Toggle circular")
    day.is_circular = payload.value
    db.commit()
    db.refresh(day)
    return day_detail(day)


@router.post("/days/{day_id}/lock")
def set_locked(day_id: int, payload: BoolValue, db: Session = Depends(get_db)):
    day = get_day_or_404(db, day_id)
    history.record(db, day.project_id, "Lock day")
    day.is_locked = payload.value
    db.commit()
    db.refresh(day)
    return day_detail(day)


@router.post("/days/{day_id}/lock-end")
def set_end_locks(
    day_id: int,
    lock_start: bool | None = Query(None),
    lock_end: bool | None = Query(None),
    db: Session = Depends(get_db),
):
    """Pin one or both ends of a day without freezing the whole route."""
    day = get_day_or_404(db, day_id)
    history.record(db, day.project_id, "Pin day end")
    if lock_start is not None:
        day.lock_start = lock_start
    if lock_end is not None:
        day.lock_end = lock_end
    db.commit()
    db.refresh(day)
    return day_detail(day)


@router.post("/days/{day_id}/rotate")
def rotate_day(day_id: int, payload: RotateRequest, db: Session = Depends(get_db)):
    day = get_day_or_404(db, day_id)
    history.record(db, day.project_id, "Rotate loop start")
    route_ops.require_unlocked(day)
    if not day.points or not (0 <= payload.index < len(day.points)):
        raise HTTPException(400, "Index out of range")
    day.points = route_ops.rotate_to_start(day.points, payload.index)
    _rebaseline(day)
    db.commit()
    db.refresh(day)
    return day_detail(day)


def _rebaseline(day: Day) -> None:
    """Forget the trimmed-away ends: the current route becomes the new full one.

    Every edit except trimming does this, because after reversing, rotating or
    handing points to a neighbour the old route is no longer a meaningful
    "before" to show underneath.
    """
    day.source_points = list(day.points or [])


@router.post("/days/{day_id}/trim")
def trim_day(day_id: int, payload: TrimRequest, db: Session = Depends(get_db)):
    """Narrow the day to a range of its current points, keeping the rest as shadow."""
    day = get_day_or_404(db, day_id)
    history.record(db, day.project_id, "Trim day")
    route_ops.require_unlocked(day)
    n = len(day.points or [])
    if not (0 <= payload.start_index < n) or not (0 <= payload.end_index < n):
        raise HTTPException(400, "Index out of range")

    # Trimming is the one edit that keeps the wider route, so it can be widened again.
    if not day.source_points:
        day.source_points = list(day.points or [])
    else:
        # The indices refer to the visible route; translate them onto the source
        # so repeated trims stay anchored to the original.
        offset = route_ops.offset_in_source(day.source_points, day.points or [])
        if offset is not None:
            payload = TrimRequest(
                start_index=payload.start_index + offset, end_index=payload.end_index + offset
            )
            day.points = route_ops.trim(day.source_points, payload.start_index, payload.end_index)
            db.commit()
            db.refresh(day)
            return day_detail(day)

    day.points = route_ops.trim(day.points, payload.start_index, payload.end_index)
    db.commit()
    db.refresh(day)
    return day_detail(day)


@router.post("/days/{day_id}/set-range")
def set_day_range(
    day_id: int,
    start_index: int = Query(..., ge=0, description="Index into the full (shadow) route"),
    end_index: int = Query(..., ge=0),
    db: Session = Depends(get_db),
):
    """Set the day's start and end anywhere on the full route, including the
    parts previously trimmed away."""
    day = get_day_or_404(db, day_id)
    history.record(db, day.project_id, "Set day range")
    route_ops.require_unlocked(day)

    source = day.source_points or day.points or []
    n = len(source)
    if not (0 <= start_index < n) or not (0 <= end_index < n):
        raise HTTPException(400, f"Index out of range (the full route has {n} points)")
    if start_index == end_index:
        raise HTTPException(400, "Start and end can't be the same point")

    if not day.source_points:
        day.source_points = list(source)
    day.points = route_ops.trim(source, start_index, end_index)
    db.commit()
    db.refresh(day)
    return day_detail(day)


@router.get("/days/{day_id}/shadow-candidates")
def shadow_candidates(day_id: int, db: Session = Depends(get_db)):
    """Other uploaded routes that could serve as this day's shadow.

    Anything overlapping this day's area is listed first, since that's almost
    always the master route you want to carve days out of.
    """
    day = get_day_or_404(db, day_id)
    mine = day.points or []
    if not mine:
        raise HTTPException(400, "Day has no points")

    lats = [p["lat"] for p in mine]
    lons = [p["lon"] for p in mine]
    my_box = (min(lats), max(lats), min(lons), max(lons))

    out = []
    for other in db.query(Day).filter(Day.id != day_id).all():
        pts = other.source_points or other.points or []
        if len(pts) < 2:
            continue
        o_lats = [p["lat"] for p in pts]
        o_lons = [p["lon"] for p in pts]
        overlaps = (
            min(o_lats) <= my_box[1]
            and max(o_lats) >= my_box[0]
            and min(o_lons) <= my_box[3]
            and max(o_lons) >= my_box[2]
        )
        out.append(
            {
                "day_id": other.id,
                "name": other.name,
                "project_id": other.project_id,
                "project_name": other.project.name if other.project else None,
                "point_count": len(pts),
                "distance_m": cumulative_distance(pts),
                "overlaps": overlaps,
                "is_longer": len(pts) > len(mine),
            }
        )

    out.sort(key=lambda c: (not c["overlaps"], not c["is_longer"], -c["distance_m"]))
    return {"day_id": day_id, "candidates": out}


@router.post("/days/{day_id}/shadow")
def set_shadow(
    day_id: int,
    from_day_id: int = Query(..., description="The uploaded route to use as the shadow"),
    db: Session = Depends(get_db),
):
    """Use another uploaded route as this day's shadow.

    The day's own points are left alone; the shadow just becomes the wider route
    its start and end can be moved along.
    """
    day = get_day_or_404(db, day_id)
    route_ops.require_unlocked(day)
    other = get_day_or_404(db, from_day_id)
    if other.id == day.id:
        raise HTTPException(400, "A day can't be its own shadow")

    source = other.source_points or other.points or []
    if len(source) < 2:
        raise HTTPException(400, "That route has no points to use")

    day.source_points = list(source)
    db.commit()
    db.refresh(day)

    detail = day_detail(day)
    # Say how well the day sits on its new shadow: a poor fit means the routes
    # only loosely follow the same ground.
    start_gap = haversine(source[detail["source_start"]], (day.points or [{}])[0])
    end_gap = haversine(source[detail["source_end"]], (day.points or [{}])[-1])
    detail["shadow_fit"] = {
        "from_day_id": other.id,
        "from_name": other.name,
        "start_gap_m": round(start_gap, 1),
        "end_gap_m": round(end_gap, 1),
        "exact": start_gap < 1 and end_gap < 1,
    }
    return detail


@router.delete("/days/{day_id}/shadow")
def clear_shadow(day_id: int, db: Session = Depends(get_db)):
    """Drop the shadow: the day's current route becomes the whole of it."""
    day = get_day_or_404(db, day_id)
    _rebaseline(day)
    db.commit()
    db.refresh(day)
    return day_detail(day)


@router.post("/days/{day_id}/restore-full")
def restore_full_route(day_id: int, db: Session = Depends(get_db)):
    """Undo trimming: bring back the whole route this day came from."""
    day = get_day_or_404(db, day_id)
    history.record(db, day.project_id, "Restore full route")
    route_ops.require_unlocked(day)
    if day.source_points:
        day.points = list(day.source_points)
        db.commit()
        db.refresh(day)
    return day_detail(day)


@router.post("/days/{day_id}/reverse")
def reverse_day(day_id: int, db: Session = Depends(get_db)):
    day = get_day_or_404(db, day_id)
    history.record(db, day.project_id, "Reverse day")
    route_ops.require_unlocked(day)
    day.points = route_ops.reverse(day.points or [])
    _rebaseline(day)
    db.commit()
    db.refresh(day)
    return day_detail(day)


def _apply_split(db: Session, day: Day, indices: list[int]):
    """Cut a day at the given indices, keeping the first chunk on the original row."""
    chunks = route_ops.split(day.points or [], indices)
    if len(chunks) < 2:
        raise HTTPException(400, "Split indices did not produce more than one day")

    project_id = day.project_id
    old_order = day.order_index
    shift = len(chunks) - 1
    siblings = db.query(Day).filter(Day.project_id == project_id, Day.order_index > old_order).all()
    for s in siblings:
        s.order_index += shift

    base_name = day.name
    result_days = []
    for i, chunk in enumerate(chunks):
        if i == 0:
            day.name = f"{base_name} (1)"
            day.points = chunk
            _rebaseline(day)
            result_days.append(day)
        else:
            new_day = Day(
                project_id=project_id,
                name=f"{base_name} ({i + 1})",
                order_index=old_order + i,
                is_circular=False,
                is_locked=False,
                points=chunk,
                source_points=list(chunk),
            )
            db.add(new_day)
            result_days.append(new_day)

    db.commit()
    for d in result_days:
        db.refresh(d)
    return [day_detail(d) for d in result_days]


@router.post("/days/{day_id}/split")
def split_day(day_id: int, payload: SplitRequest, db: Session = Depends(get_db)):
    day = get_day_or_404(db, day_id)
    history.record(db, day.project_id, "Split day")
    route_ops.require_unlocked(day)
    return _apply_split(db, day, payload.indices)


@router.post("/days/{day_id}/split-even")
def split_day_evenly(
    day_id: int,
    parts: int = Query(..., ge=2, le=20, description="How many days to end up with"),
    climb_weight: float = Query(
        0.0, ge=0, le=3, description="0 splits on distance; 1 makes hilly days shorter"
    ),
    db: Session = Depends(get_db),
):
    """Split one day into several of roughly equal effort."""
    day = get_day_or_404(db, day_id)
    history.record(db, day.project_id, "Split evenly")
    route_ops.require_unlocked(day)
    indices = route_ops.even_split_indices(day.points or [], parts, climb_weight)
    if not indices:
        raise HTTPException(400, f"Not enough points to split into {parts} parts")
    return _apply_split(db, day, indices)


@router.post("/days/merge")
def merge_days(payload: MergeRequest, db: Session = Depends(get_db)):
    a = get_day_or_404(db, payload.day_id_a)
    b = get_day_or_404(db, payload.day_id_b)
    if a.project_id != b.project_id:
        raise HTTPException(400, "Days belong to different projects")
    if a.is_locked or b.is_locked:
        raise HTTPException(409, "Cannot merge: one of the days is locked")
    history.record(db, a.project_id, "Merge days")

    lo, hi = (a, b) if a.order_index < b.order_index else (b, a)
    lo.points = route_ops.merge(lo.points or [], hi.points or [])
    _rebaseline(lo)
    for c in list(hi.connectors):
        c.day_id = lo.id

    project_id = lo.project_id
    hi_order = hi.order_index
    db.delete(hi)
    db.flush()

    siblings = db.query(Day).filter(Day.project_id == project_id, Day.order_index > hi_order).all()
    for s in siblings:
        s.order_index -= 1

    db.commit()
    db.refresh(lo)
    return day_detail(lo)


@router.get("/days/{day_id}/weather")
def day_weather(
    day_id: int,
    target_date: date | None = Query(None),
    db: Session = Depends(get_db),
):
    """Forecast for the day's route, with wind resolved against the direction of travel."""
    day = get_day_or_404(db, day_id)
    points = day.points or []
    if len(points) < 2:
        raise HTTPException(400, "Day has too few points")

    when = target_date or date.today()
    days_ahead = (when - date.today()).days
    if days_ahead < 0:
        raise HTTPException(400, "That date is in the past; this is a forecast only")
    if days_ahead > weather.FORECAST_DAYS:
        raise HTTPException(
            400,
            f"{when.isoformat()} is {days_ahead} days ahead; forecasts only reach "
            f"{weather.FORECAST_DAYS} days.",
        )

    mid = points[len(points) // 2]
    try:
        data = weather.fetch(mid["lat"], mid["lon"], when)
    except Exception as exc:
        raise HTTPException(502, f"Could not reach the weather service: {exc}") from exc

    daily = data.get("daily", {})

    def first(key):
        values = daily.get(key) or []
        return values[0] if values else None

    wind_from = first("wind_direction_10m_dominant")
    wind_kmh = first("wind_speed_10m_max")

    # Overall heading, plus a few legs so a route that turns shows both.
    overall = weather.bearing(points[0], points[-1])
    legs = []
    chunk = max(1, len(points) // 4)
    for i in range(0, len(points) - chunk, chunk):
        a, b = points[i], points[min(i + chunk, len(points) - 1)]
        brg = weather.bearing(a, b)
        legs.append(
            {
                "from_index": i,
                "heading_deg": round(brg),
                "heading": weather.compass(brg),
                "wind": weather.wind_effect(brg, wind_from, wind_kmh)
                if wind_from is not None and wind_kmh is not None
                else None,
            }
        )

    return {
        "day_id": day_id,
        "day_name": day.name,
        "date": when.isoformat(),
        "summary": weather.describe(first("weather_code")),
        "temp_min_c": first("temperature_2m_min"),
        "temp_max_c": first("temperature_2m_max"),
        "precip_mm": first("precipitation_sum"),
        "precip_chance_pct": first("precipitation_probability_max"),
        "wind_kmh": wind_kmh,
        "gust_kmh": first("wind_gusts_10m_max"),
        "wind_from_deg": wind_from,
        "wind_from": weather.compass(wind_from) if wind_from is not None else None,
        "sunrise": first("sunrise"),
        "sunset": first("sunset"),
        "route_heading_deg": round(overall),
        "route_heading": weather.compass(overall),
        "overall_wind": weather.wind_effect(overall, wind_from, wind_kmh)
        if wind_from is not None and wind_kmh is not None
        else None,
        "legs": legs,
    }


@router.get("/days/{day_id}/export")
def export_day(day_id: int, include_connectors: bool = True, db: Session = Depends(get_db)):
    day = get_day_or_404(db, day_id)
    segments = day_export_segments(day, include_connectors=include_connectors)
    xml = build_gpx(day.name, segments)
    return Response(
        content=xml,
        media_type="application/gpx+xml",
        headers={"Content-Disposition": f'attachment; filename="{slugify(day.name)}.gpx"'},
    )
