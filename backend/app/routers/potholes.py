from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete as sa_delete
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..geo import distance_to_route, haversine
from ..models import Day, Pothole, PotholeArea
from ..mvt import tile_bounds, tile_for_lonlat
from ..pothole_fetch import BASE, estimate_report_date, fetch_boxes, pothole_categories

router = APIRouter(tags=["potholes"])


@router.get("/potholes")
def status(db: Session = Depends(get_db)):
    newest = db.query(func.max(Pothole.fetched_at)).scalar()
    saturated = db.query(PotholeArea).filter(PotholeArea.saturated.is_(True)).count()
    return {
        "total": db.query(Pothole).count(),
        "areas_fetched": db.query(PotholeArea).count(),
        "areas_saturated": saturated,
        "last_fetch": newest.isoformat() if newest else None,
        "categories": len(pothole_categories()),
    }


@router.delete("/potholes", status_code=204)
def clear(db: Session = Depends(get_db)):
    db.execute(sa_delete(Pothole))
    db.execute(sa_delete(PotholeArea))
    db.commit()


@router.post("/days/{day_id}/potholes/fetch")
def fetch_for_day(
    day_id: int,
    z: int = Query(13, ge=10, le=15, description="Higher means smaller boxes and more requests"),
    max_boxes: int = Query(120, ge=1, le=400),
    delay_ms: int = Query(300, ge=0, le=5000),
    max_age_hours: float = Query(24.0, ge=0),
    db: Session = Depends(get_db),
):
    """Ask FixMyStreet about the boxes this day's route passes through."""
    day = db.get(Day, day_id)
    if not day:
        raise HTTPException(404, "Day not found")
    points = day.points or []
    if not points:
        raise HTTPException(400, "Day has no points")

    tiles = sorted({tile_for_lonlat(p["lat"], p["lon"], z) for p in points})
    if len(tiles) > max_boxes:
        raise HTTPException(
            400,
            f"This route covers {len(tiles)} boxes at z{z}, above the {max_boxes} limit. "
            f"Use a lower zoom for fewer, larger boxes.",
        )

    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=max_age_hours)
    known = {a.box: a for a in db.query(PotholeArea).all()}

    boxes: list[tuple[float, float, float, float]] = []
    keys: dict[tuple[float, float, float, float], str] = {}
    skipped = 0
    for x, y in tiles:
        south, west, north, east = tile_bounds(z, x, y)
        box = (west, south, east, north)
        key = f"{z}/{x}/{y}"
        area = known.get(key)
        if area is not None and area.fetched_at >= cutoff:
            skipped += 1
            continue
        boxes.append(box)
        keys[box] = key

    found = new = 0
    saturated = 0
    failures: list[str] = []
    seen: set[str] = set()

    for box, pins, is_saturated, error in fetch_boxes(boxes, delay_s=delay_ms / 1000.0):
        key = keys[box]
        if error:
            failures.append(f"{key}: {error}")
            continue
        if is_saturated:
            saturated += 1

        for pin in pins:
            found += 1
            if pin["report_id"] in seen:
                continue
            seen.add(pin["report_id"])
            existing = (
                db.query(Pothole)
                .filter(Pothole.source == "fixmystreet", Pothole.report_id == pin["report_id"])
                .one_or_none()
            )
            target = existing or Pothole(source="fixmystreet", report_id=pin["report_id"])
            target.title = pin["title"]
            target.colour = pin["colour"]
            target.lat = pin["lat"]
            target.lon = pin["lon"]
            target.url = f"{BASE}/report/{pin['report_id']}"
            target.fetched_at = datetime.now(UTC).replace(tzinfo=None)
            if existing is None:
                db.add(target)
                new += 1

        area = known.get(key) or PotholeArea(box=key)
        area.pin_count = len(pins)
        area.saturated = is_saturated
        area.fetched_at = datetime.now(UTC).replace(tzinfo=None)
        if area.id is None:
            db.add(area)

    db.commit()
    return {
        "day_id": day_id,
        "day_name": day.name,
        "zoom": z,
        "boxes_required": len(tiles),
        "boxes_cached": skipped,
        "boxes_fetched": len(boxes) - len(failures),
        "boxes_saturated": saturated,
        "pins_seen": found,
        "new_reports": new,
        "total_stored": db.query(Pothole).count(),
        "failures": failures[:10],
    }


@router.get("/days/{day_id}/potholes")
def potholes_for_day(
    day_id: int,
    buffer_m: float = Query(100.0, ge=0, le=25000),
    max_age_years: float = Query(
        2.0, ge=0, le=25, description="Drop reports older than this (estimated from report id)"
    ),
    db: Session = Depends(get_db),
):
    day = db.get(Day, day_id)
    if not day:
        raise HTTPException(404, "Day not found")
    points = day.points or []
    if not points:
        return {"day_id": day_id, "matches": []}

    lats = [p["lat"] for p in points]
    lons = [p["lon"] for p in points]
    pad = buffer_m / 111_320.0 * 2 + 0.001
    candidates = (
        db.query(Pothole)
        .filter(
            Pothole.lat >= min(lats) - pad,
            Pothole.lat <= max(lats) + pad,
            Pothole.lon >= min(lons) - pad,
            Pothole.lon <= max(lons) + pad,
        )
        .all()
    )

    # Same cheap rejection as the roadworks check: test against a subsampled route
    # before measuring against every point.
    step = max(1, len(points) // 250)
    sample = points[::step] + [points[-1]]
    max_gap = max((haversine(sample[i - 1], sample[i]) for i in range(1, len(sample))), default=0.0)
    slack = buffer_m + max_gap

    oldest_allowed = date.today() - timedelta(days=int(max_age_years * 365.25))
    too_old = 0
    matches = []
    for hole in candidates:
        probe = {"lat": hole.lat, "lon": hole.lon}
        if min(haversine(probe, s) for s in sample) > slack:
            continue
        dist, idx = distance_to_route(hole.lat, hole.lon, points)
        if dist > buffer_m:
            continue
        reported = estimate_report_date(hole.report_id)
        if reported and max_age_years and reported < oldest_allowed:
            too_old += 1
            continue

        matches.append(
            {
                "report_id": hole.report_id,
                "title": hole.title,
                "reported_approx": reported.isoformat() if reported else None,
                "url": hole.url,
                "lat": hole.lat,
                "lon": hole.lon,
                "distance_m": round(dist, 1),
                "nearest_point_index": idx,
            }
        )

    matches.sort(key=lambda m: m["distance_m"])
    return {
        "day_id": day_id,
        "day_name": day.name,
        "buffer_m": buffer_m,
        "candidates_checked": len(candidates),
        "excluded_too_old": too_old,
        "max_age_years": max_age_years,
        "total_stored": db.query(Pothole).count(),
        "matches": matches,
    }
