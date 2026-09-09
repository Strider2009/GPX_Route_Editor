from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete as sa_delete
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import roadworks_ref as ref
from ..database import get_db
from ..geo import distance_to_route, haversine
from ..models import Day, Roadwork, TileCache
from ..mvt import decode_tile, tile_for_lonlat
from ..tile_fetch import fetch_tiles

router = APIRouter(tags=["roadworks"])

# Attribute names as they appear in one.network tile features.
ATTR_MAP = {
    "road_name": "road_name",
    "works_desc": "works_desc",
    "resporg_name": "resporg_name",
    "pub_name": "pub_name",
    "permit_ref": "permit_ref",
    "works_ref": "works_ref",
    "traffic_management": "traffman",
    "delay": "delay",
    "tm_cat": "tm_cat",
    "item_type": "itemtype_label",
}
INT_ATTRS = {"impact": "impact", "works_state": "works_state", "permit_status": "permit_status"}


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_dt(value: str | None):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _import_features(
    db: Session, features: list[dict], source: str, seen: dict[str, Roadwork] | None = None
) -> tuple[int, int, int]:
    """Upsert decoded tile features. Returns (imported, updated, skipped).

    Pass a shared `seen` across tiles: a work near a tile edge appears in every
    tile it touches, and pending inserts aren't visible to a fresh query.
    """
    imported = updated = skipped = 0
    if seen is None:
        seen = {}

    for feat in features:
        attrs = feat["attrs"]
        external_id = attrs.get("id")
        coords = feat["coords"]
        # Basemap layers (water, place, ...) also carry an 'id', so require
        # attributes that only a roadworks record has.
        looks_like_work = any(
            attrs.get(k) is not None
            for k in ("start_date", "end_date", "traffman", "works_ref", "permit_ref")
        )
        if external_id is None or not coords or not looks_like_work:
            skipped += 1
            continue

        external_id = str(external_id)

        if external_id in seen:
            target = seen[external_id]
            merged = (target.geometry or []) + [[lat, lon] for lat, lon in coords]
            target.geometry = merged
            target.min_lat = min(p[0] for p in merged)
            target.max_lat = max(p[0] for p in merged)
            target.min_lon = min(p[1] for p in merged)
            target.max_lon = max(p[1] for p in merged)
            continue

        lats = [c[0] for c in coords]
        lons = [c[1] for c in coords]

        existing = (
            db.query(Roadwork)
            .filter(Roadwork.source == source, Roadwork.external_id == external_id)
            .one_or_none()
        )
        target = existing or Roadwork(source=source, external_id=external_id)
        seen[external_id] = target

        target.layer = feat["layer"]
        for field, key in ATTR_MAP.items():
            setattr(target, field, attrs.get(key))
        for field, key in INT_ATTRS.items():
            setattr(target, field, _as_int(attrs.get(key)))
        target.start_date = attrs.get("start_date")
        target.end_date = attrs.get("end_date")
        target.geometry = [[lat, lon] for lat, lon in coords]
        target.min_lat, target.max_lat = min(lats), max(lats)
        target.min_lon, target.max_lon = min(lons), max(lons)
        target.attrs = dict(attrs)

        if existing:
            updated += 1
        else:
            db.add(target)
            imported += 1

    return imported, updated, skipped


@router.get("/roadworks")
def list_roadworks(db: Session = Depends(get_db)):
    tiles = db.query(TileCache).count()
    tile_bytes = db.query(func.coalesce(func.sum(TileCache.byte_size), 0)).scalar() or 0
    newest = db.query(func.max(TileCache.fetched_at)).scalar()
    return {
        "total": db.query(Roadwork).count(),
        "cached_tiles": tiles,
        "cached_bytes": int(tile_bytes),
        "last_fetch": newest.isoformat() if newest else None,
    }


@router.delete("/roadworks", status_code=204)
def clear_roadworks(db: Session = Depends(get_db)):
    """Drop imported works and the tile cache together, so a re-check starts clean."""
    db.execute(sa_delete(Roadwork))
    db.execute(sa_delete(TileCache))
    db.commit()


@router.get("/days/{day_id}/roadworks")
def roadworks_for_day(
    day_id: int,
    target_date: date | None = Query(None, description="Only works active on this date"),
    buffer_m: float = Query(
        100.0, ge=0, le=25000, description="How close to the route counts as a hit"
    ),
    min_relevance: str = Query("low", pattern="^(none|low|medium|high)$"),
    sort_by: str = Query("distance", pattern="^(distance|relevance)$"),
    include_inactive: bool = Query(False, description="Include completed/cancelled works"),
    db: Session = Depends(get_db),
):
    day = db.get(Day, day_id)
    if not day:
        raise HTTPException(404, "Day not found")
    points = day.points or []
    if not points:
        return {"day_id": day_id, "target_date": target_date, "matches": []}

    lats = [p["lat"] for p in points]
    lons = [p["lon"] for p in points]
    # Rough degree padding for the buffer, generous at UK latitudes.
    pad = buffer_m / 111_320.0 * 2 + 0.001
    candidates = (
        db.query(Roadwork)
        .filter(
            Roadwork.max_lat >= min(lats) - pad,
            Roadwork.min_lat <= max(lats) + pad,
            Roadwork.max_lon >= min(lons) - pad,
            Roadwork.min_lon <= max(lons) + pad,
        )
        .all()
    )

    day_start = (
        datetime.combine(target_date, datetime.min.time(), tzinfo=UTC) if target_date else None
    )
    day_end = day_start + timedelta(days=1) if day_start else None
    threshold = ref.RELEVANCE_ORDER[min_relevance]

    # Scanning every route point for every work is O(points x works), which hurts on a
    # 5000-point route. Cheaply reject far-away works against a subsampled route first;
    # the max gap between samples makes the rejection conservative.
    step = max(1, len(points) // 250)
    sample = points[::step] + [points[-1]]
    max_gap = 0.0
    for i in range(1, len(sample)):
        max_gap = max(max_gap, haversine(sample[i - 1], sample[i]))
    slack = buffer_m + max_gap

    matches = []
    for work in candidates:
        if not include_inactive and work.works_state in ref.INACTIVE_WORKS_STATES:
            continue

        relevance = ref.cycling_relevance(work.traffic_management, work.item_type)
        if ref.RELEVANCE_ORDER[relevance] < threshold:
            continue

        if day_start is not None:
            starts = _parse_dt(work.start_date)
            ends = _parse_dt(work.end_date)
            if starts and starts >= day_end:
                continue
            if ends and ends < day_start:
                continue

        best = None
        for lat, lon in work.geometry or []:
            probe = {"lat": lat, "lon": lon}
            if min(haversine(probe, s) for s in sample) > slack:
                continue
            dist, idx = distance_to_route(lat, lon, points)
            if best is None or dist < best[0]:
                best = (dist, idx, lat, lon)
        if best is None or best[0] > buffer_m:
            continue

        dist, idx, lat, lon = best
        matches.append(
            {
                "external_id": work.external_id,
                "road_name": work.road_name,
                "works_desc": work.works_desc,
                "responsible_org": work.resporg_name,
                "permit_ref": work.permit_ref,
                "start_date": work.start_date,
                "end_date": work.end_date,
                "traffic_management": work.traffic_management or work.item_type,
                "item_type": work.item_type,
                "delay": work.delay,
                "tm_cat": work.tm_cat,
                "impact": ref.label(ref.IMPACT, work.impact),
                "works_state": ref.label(ref.WORKS_STATE, work.works_state),
                "permit_status": ref.label(ref.PERMIT_STATUS, work.permit_status),
                "cycling_relevance": relevance,
                "distance_m": round(dist, 1),
                "nearest_point_index": idx,
                "lat": lat,
                "lon": lon,
                "geometry": work.geometry,
            }
        )

    if sort_by == "relevance":
        matches.sort(key=lambda m: (-ref.RELEVANCE_ORDER[m["cycling_relevance"]], m["distance_m"]))
    else:
        matches.sort(key=lambda m: (m["distance_m"], -ref.RELEVANCE_ORDER[m["cycling_relevance"]]))
    return {
        "day_id": day_id,
        "day_name": day.name,
        "target_date": target_date,
        "buffer_m": buffer_m,
        "candidates_checked": len(candidates),
        # Lets the UI distinguish "nothing imported" from "nothing near this route".
        "total_stored": db.query(Roadwork).count(),
        "matches": matches,
    }


@router.post("/days/{day_id}/roadworks/fetch")
def fetch_roadworks_for_day(
    day_id: int,
    target_date: date | None = Query(None, description="Date to ask the tile server about"),
    z: int = Query(11, ge=8, le=14),
    max_tiles: int = Query(40, ge=1, le=120),
    delay_ms: int = Query(250, ge=0, le=5000),
    max_age_hours: float = Query(12.0, ge=0, description="Reuse cached tiles younger than this"),
    db: Session = Depends(get_db),
):
    """Fetch the tiles covering this day's route, reusing cached ones, then import.

    The tile list comes from the route geometry, so this asks for the minimum
    needed rather than crawling an area, and a repeat check costs no requests at all.
    """
    day = db.get(Day, day_id)
    if not day:
        raise HTTPException(404, "Day not found")
    points = day.points or []
    if not points:
        raise HTTPException(400, "Day has no points")

    tiles = sorted({tile_for_lonlat(p["lat"], p["lon"], z) for p in points})
    if len(tiles) > max_tiles:
        raise HTTPException(
            400,
            f"This route needs {len(tiles)} tiles at z{z}, above the {max_tiles} limit. "
            f"Use a lower zoom, or raise max_tiles deliberately.",
        )

    the_date = target_date or date.today()
    date_key = the_date.isoformat()
    when = datetime.combine(the_date, datetime.min.time())
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=max_age_hours)

    # Work out what we already hold before touching the network.
    cached_rows = {
        (row.z, row.x, row.y): row
        for row in db.query(TileCache)
        .filter(TileCache.z == z, TileCache.target_date == date_key)
        .all()
    }
    to_fetch: list[tuple[int, int, int]] = []
    usable: dict[tuple[int, int, int], bytes] = {}
    for x, y in tiles:
        row = cached_rows.get((z, x, y))
        if row is not None and row.fetched_at >= cutoff:
            usable[(z, x, y)] = row.data
        else:
            to_fetch.append((z, x, y))

    failures: list[str] = []
    for z_, x_, y_, data, error in fetch_tiles(to_fetch, when, delay_s=delay_ms / 1000.0):
        if error:
            failures.append(f"{z_}/{x_}/{y_}: {error}")
            continue
        data = data or b""
        usable[(z_, x_, y_)] = data
        row = cached_rows.get((z_, x_, y_))
        if row is None:
            row = TileCache(z=z_, x=x_, y=y_, target_date=date_key)
            db.add(row)
        row.data = data
        row.byte_size = len(data)
        row.fetched_at = datetime.now(UTC).replace(tzinfo=None)

    seen: dict[str, Roadwork] = {}
    imported = updated = skipped = 0
    empty = 0
    for (z_, x_, y_), data in sorted(usable.items()):
        if not data:
            empty += 1  # a square with no works in it, which is normal
            continue
        try:
            features = decode_tile(data, z_, x_, y_)
        except Exception as exc:
            failures.append(f"{z_}/{x_}/{y_}: decode failed: {exc}")
            continue
        i, u, s = _import_features(db, features, "tile-fetch", seen)
        imported += i
        updated += u
        skipped += s

    db.commit()
    return {
        "day_id": day_id,
        "day_name": day.name,
        "target_date": the_date,
        "zoom": z,
        "tiles_required": len(tiles),
        "tiles_from_cache": len(tiles) - len(to_fetch),
        "tiles_fetched": len(to_fetch) - len(failures),
        "tiles_empty": empty,
        "imported": imported,
        "updated": updated,
        "skipped_non_works": skipped,
        "total_stored": db.query(Roadwork).count(),
        "failures": failures[:10],
    }


@router.get("/days/{day_id}/roadworks/tiles")
def tiles_for_day(day_id: int, z: int = Query(10, ge=1, le=20), db: Session = Depends(get_db)):
    """Which map tiles cover this day - i.e. which ones to save from the browser."""
    day = db.get(Day, day_id)
    if not day:
        raise HTTPException(404, "Day not found")
    points = day.points or []
    if not points:
        return {"day_id": day_id, "z": z, "tiles": []}

    tiles = sorted({tile_for_lonlat(p["lat"], p["lon"], z) for p in points})
    return {
        "day_id": day_id,
        "day_name": day.name,
        "z": z,
        "count": len(tiles),
        "tiles": [{"z": z, "x": x, "y": y} for x, y in tiles],
    }
