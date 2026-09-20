"""Rider briefings for a day.

The facts endpoint is free and always available; the written one costs an API
call and is kept separate so the panel stays useful without a key.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import briefing as briefing_mod
from ..database import get_db
from ..models import Day, NarrativeCache, PlaceLookup

router = APIRouter(tags=["briefing"])


def _get_day_or_404(db: Session, day_id: int) -> Day:
    day = db.get(Day, day_id)
    if not day:
        raise HTTPException(404, "Day not found")
    return day


@router.get("/days/{day_id}/briefing")
def day_briefing(
    day_id: int,
    include_places: bool = Query(True, description="Look up settlement names along the route"),
    buffer_m: int = Query(100, ge=50, le=5000),
    spacing_km: float = Query(10.0, ge=0, le=100, description="At most one place per this many km"),
    refresh: bool = Query(False, description="Ignore the cached place lookup and re-ask"),
    db: Session = Depends(get_db),
):
    """The measured facts: distance, climbs, places, stops."""
    day = _get_day_or_404(db, day_id)
    return briefing_mod.gather(
        day,
        include_places=include_places,
        buffer_m=buffer_m,
        spacing_km=spacing_km,
        db=db,
        refresh=refresh,
    )


@router.post("/days/{day_id}/briefing/narrative")
def day_briefing_narrative(
    day_id: int,
    include_places: bool = Query(True),
    buffer_m: int = Query(100, ge=50, le=5000),
    spacing_km: float = Query(10.0, ge=0, le=100),
    effort: str = Query("medium", pattern="^(low|medium|high)$"),
    refresh: bool = Query(False, description="Rewrite even if these exact facts are cached"),
    db: Session = Depends(get_db),
):
    """The same facts, written up. Costs one model call unless already cached."""
    day = _get_day_or_404(db, day_id)
    facts = briefing_mod.gather(
        day, include_places=include_places, buffer_m=buffer_m, spacing_km=spacing_km, db=db
    )
    try:
        text = briefing_mod.narrate(facts, effort=effort, db=db, refresh=refresh)
    except briefing_mod.BriefingUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"day_id": day.id, "facts": facts, "briefing": text}


@router.get("/briefing/cache")
def briefing_cache_status(db: Session = Depends(get_db)):
    """What is currently cached, so it can be cleared knowingly."""
    narratives = db.query(NarrativeCache).count()
    lookups = db.query(PlaceLookup).count()
    newest = (
        db.query(NarrativeCache).order_by(NarrativeCache.created_at.desc()).first()
        if narratives
        else None
    )
    return {
        "narratives": narratives,
        "place_lookups": lookups,
        "newest_narrative_at": newest.created_at if newest else None,
    }


@router.delete("/briefing/cache")
def clear_briefing_cache(
    narratives: bool = Query(True, description="Clear written briefings"),
    places: bool = Query(True, description="Clear settlement lookups"),
    db: Session = Depends(get_db),
):
    """Throw away cached briefings so the next request rebuilds them.

    Clearing places costs an Overpass query next time; clearing narratives costs
    a model call. Both are opt-out so a targeted clear is possible.
    """
    removed = {"narratives": 0, "place_lookups": 0}
    if narratives:
        removed["narratives"] = db.query(NarrativeCache).delete()
    if places:
        removed["place_lookups"] = db.query(PlaceLookup).delete()
    db.commit()
    return removed
