"""Moving the joins between consecutive days.

A boundary is one shared point: the end of one day and the start of the next are
the same location, so moving it changes both together. It can only move when
both sides permit it, which is why locking either neighbour freezes it - and why
a two-day trip with one locked day has no movable boundary at all.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import history, route_ops
from ..database import get_db
from ..geo import haversine
from ..models import Day, Project
from ..serializers import day_summary

router = APIRouter(tags=["boundaries"])


def _ordered_days(db: Session, project_id: int) -> list[Day]:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return sorted(project.days, key=lambda d: d.order_index)


JOIN_TOLERANCE_M = 25.0


def _joins(a: Day, b: Day) -> bool:
    """Do these days actually meet? Reordering can leave neighbours unconnected."""
    pa, pb = a.points or [], b.points or []
    if not pa or not pb:
        return False
    return haversine(pa[-1], pb[0]) <= JOIN_TOLERANCE_M


def is_loop(days: list[Day]) -> bool:
    """Does the trip come back to where it started?

    On a loop the first day's start and the last day's end are the same place,
    so they form a boundary like any other - it just wraps round the end of the
    list rather than sitting between two consecutive days.
    """
    if len(days) < 2:
        return False
    first, last = days[0].points or [], days[-1].points or []
    if not first or not last:
        return False
    return haversine(last[-1], first[0]) <= JOIN_TOLERANCE_M


def boundary_pairs(days: list[Day]) -> list[tuple[Day, Day]]:
    """The (earlier, later) day for each boundary, including the wrap on a loop."""
    pairs = [(days[i], days[i + 1]) for i in range(len(days) - 1)]
    if is_loop(days):
        pairs.append((days[-1], days[0]))
    return pairs


def _blockers(a: Day, b: Day) -> list[str]:
    """Why this boundary can't move, in words the UI can show."""
    reasons = []
    if not _joins(a, b):
        # Sliding a boundary only means anything when one day ends where the next
        # begins; otherwise there's nothing to hand across.
        reasons.append("these days don't join end to end")
    if a.is_locked:
        reasons.append(f"'{a.name}' is locked")
    elif a.lock_end:
        reasons.append(f"the end of '{a.name}' is pinned")
    if b.is_locked:
        reasons.append(f"'{b.name}' is locked")
    elif b.lock_start:
        reasons.append(f"the start of '{b.name}' is pinned")
    return reasons


def _describe(index: int, a: Day, b: Day) -> dict:
    reasons = _blockers(a, b)
    back, forward = route_ops.boundary_range(a.points or [], b.points or [])
    shared = (a.points or [{}])[-1]
    return {
        "index": index,
        "day_a_id": a.id,
        "day_b_id": b.id,
        "day_a_name": a.name,
        "day_b_name": b.name,
        "lat": shared.get("lat"),
        "lon": shared.get("lon"),
        "joins": _joins(a, b),
        "movable": not reasons,
        "blocked_by": reasons,
        "max_back_m": round(back, 1) if not reasons else 0.0,
        "max_forward_m": round(forward, 1) if not reasons else 0.0,
        "day_a_distance_m": route_ops.cumulative_distance(a.points or []),
        "day_b_distance_m": route_ops.cumulative_distance(b.points or []),
    }


@router.get("/projects/{project_id}/boundaries")
def list_boundaries(project_id: int, db: Session = Depends(get_db)):
    days = _ordered_days(db, project_id)
    pairs = boundary_pairs(days)
    boundaries = [_describe(i, a, b) for i, (a, b) in enumerate(pairs)]
    looped = is_loop(days)
    if looped and boundaries:
        boundaries[-1]["wraps"] = True
    for b in boundaries[:-1] if looped else boundaries:
        b["wraps"] = False
    return {
        "project_id": project_id,
        "day_count": len(days),
        "is_loop": looped,
        "movable_count": sum(1 for b in boundaries if b["movable"]),
        "boundaries": boundaries,
    }


def shift_days(days: list[Day], delta_m: float) -> tuple[int, float, list[dict]]:
    """Slide every movable boundary by delta_m, in place.

    Kept separate from the endpoint so the ordering rules can be tested directly:
    this is the code that must not go back to pairing only consecutive days.
    Returns (boundaries moved, total distance moved, the ones that were held).
    """
    # The same list the UI shows, so a wrap boundary shifts along with the rest.
    pairs = boundary_pairs(days)

    # Later boundaries first when moving forward, so a boundary never has to step
    # over ground another one is still about to give up.
    order = range(len(pairs) - 1, -1, -1) if delta_m > 0 else range(len(pairs))

    moved_total = 0.0
    applied = 0
    skipped: list[dict] = []
    for i in order:
        a, b = pairs[i]
        reasons = _blockers(a, b)
        if reasons:
            skipped.append({"index": i, "blocked_by": reasons})
            continue
        moved = _move(a, b, delta_m)
        if moved:
            applied += 1
            moved_total += moved
    return applied, moved_total, skipped


def _move(a: Day, b: Day, delta_m: float) -> float:
    """Hand points across the boundary the two days share."""
    new_a, new_b, moved = route_ops.move_boundary(a.points or [], b.points or [], delta_m)
    if moved:
        a.points = new_a
        b.points = new_b
        # Points changed hands, so neither day's old route is a meaningful shadow.
        a.source_points = list(new_a)
        b.source_points = list(new_b)
    return moved


@router.post("/projects/{project_id}/boundaries/{index}/move")
def move_boundary(
    project_id: int,
    index: int,
    delta_m: float = Query(..., description="Positive lengthens the earlier day"),
    db: Session = Depends(get_db),
):
    days = _ordered_days(db, project_id)
    pairs = boundary_pairs(days)
    if not (0 <= index < len(pairs)):
        raise HTTPException(404, "No such boundary")

    a, b = pairs[index]
    reasons = _blockers(a, b)
    if reasons:
        raise HTTPException(409, "This boundary can't move: " + ", and ".join(reasons))

    history.record(db, project_id, "Move day boundary")
    moved = _move(a, b, delta_m)
    db.commit()
    db.refresh(a)
    db.refresh(b)
    return {
        "moved_m": round(moved, 1),
        "requested_m": delta_m,
        "days": [day_summary(a), day_summary(b)],
        "boundary": _describe(index, a, b),
    }


@router.post("/projects/{project_id}/boundaries/set-edge")
def set_day_edge(
    project_id: int,
    day_id: int = Query(..., description="The day whose edge is being set"),
    edge: str = Query(..., pattern="^(start|end)$"),
    point_day_id: int = Query(..., description="Which day the chosen point belongs to"),
    point_index: int = Query(..., ge=0, description="Index into that day's points"),
    db: Session = Depends(get_db),
):
    """Put a day's start or end on a specific point.

    Where a day has a neighbour on that side, its edge *is* the shared boundary,
    so the points between the old and new position move to the neighbour rather
    than being discarded. The chosen point may lie in either of the two days.
    """
    days = _ordered_days(db, project_id)
    positions = {d.id: i for i, d in enumerate(days)}
    if day_id not in positions or point_day_id not in positions:
        raise HTTPException(404, "Day not found in this project")

    here = positions[day_id]
    looped = is_loop(days)
    neighbour = here - 1 if edge == "start" else here + 1
    if not (0 <= neighbour < len(days)):
        # On a loop the ends meet, so the first day's start and the last day's
        # end are two sides of the same boundary.
        if looped:
            neighbour = len(days) - 1 if edge == "start" else 0
        else:
            raise HTTPException(
                400,
                f"This day has no day before/after it, so its {edge} isn't a shared boundary. "
                "Trim it instead.",
            )

    # a is always the earlier of the pair, so the shared point is a's end and b's start.
    a, b = (days[neighbour], days[here]) if edge == "start" else (days[here], days[neighbour])
    if positions[point_day_id] not in (positions[a.id], positions[b.id]):
        raise HTTPException(
            400, "That point isn't on either of the two days that meet at this boundary."
        )

    reasons = _blockers(a, b)
    if reasons:
        raise HTTPException(409, "This boundary can't move: " + ", and ".join(reasons))

    history.record(db, project_id, f"Set day {edge}")
    pa, pb = a.points or [], b.points or []
    if point_day_id == a.id:
        if not (0 <= point_index < len(pa)):
            raise HTTPException(400, "Point index out of range")
        if point_index + 1 < route_ops.MIN_DAY_POINTS:
            raise HTTPException(400, "That would leave the earlier day too short")
        new_a = pa[: point_index + 1]
        new_b = [dict(p) for p in pa[point_index:]] + pb[1:]
    else:
        if not (0 <= point_index < len(pb)):
            raise HTTPException(400, "Point index out of range")
        if len(pb) - point_index < route_ops.MIN_DAY_POINTS:
            raise HTTPException(400, "That would leave the later day too short")
        new_a = pa + [dict(p) for p in pb[1 : point_index + 1]]
        new_b = pb[point_index:]

    a.points, b.points = new_a, new_b
    a.source_points, b.source_points = list(new_a), list(new_b)
    db.commit()
    db.refresh(a)
    db.refresh(b)
    return {
        "days": [day_summary(a), day_summary(b)],
        "boundary": _describe(min(here, neighbour), a, b),
    }


@router.post("/projects/{project_id}/boundaries/shift")
def shift_all_boundaries(
    project_id: int,
    delta_m: float = Query(..., description="Applied to every movable boundary"),
    db: Session = Depends(get_db),
):
    """Slide every movable boundary along the route by the same distance.

    Locked days act as anchors: their boundaries stay put and the days either
    side simply absorb the change.

    On a loop this includes the boundary that wraps round the end of the list -
    the first day's start and the last day's end are the same shared point, so
    leaving it out would rotate every join except that one.
    """
    days = _ordered_days(db, project_id)
    if len(days) < 2:
        raise HTTPException(400, "Nothing to shift: the project has one day")

    history.record(db, project_id, "Shift all boundaries")
    applied, moved_total, skipped = shift_days(days, delta_m)
    db.commit()
    refreshed = _ordered_days(db, project_id)
    return {
        "boundaries_moved": applied,
        "boundaries_skipped": skipped,
        "average_moved_m": round(moved_total / applied, 1) if applied else 0.0,
        "days": [day_summary(d) for d in refreshed],
    }
