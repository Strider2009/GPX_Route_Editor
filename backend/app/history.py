"""Undo/redo by snapshotting a project's days.

Inverse operations would be fragile here: splitting creates day rows, merging
deletes one, and a boundary move rewrites two at once. Snapshotting the whole
project sidesteps all of that and is always exactly right. The point arrays
compress about 7x, so a snapshot of a large trip costs well under 100 KB.
"""

import json
import zlib

from sqlalchemy.orm import Session

from .models import Connector, Day, HistorySnapshot, Project

# Plenty for a working session without letting the database grow unbounded.
MAX_ENTRIES = 40


def _day_state(day: Day) -> dict:
    return {
        "id": day.id,
        "name": day.name,
        "order_index": day.order_index,
        "is_circular": day.is_circular,
        "is_locked": day.is_locked,
        "lock_start": day.lock_start,
        "lock_end": day.lock_end,
        "points": day.points or [],
        "source_points": day.source_points or [],
        "connectors": [
            {"id": c.id, "name": c.name, "type": c.type, "points": c.points or []}
            for c in day.connectors
        ],
    }


def capture(db: Session, project_id: int) -> bytes:
    project = db.get(Project, project_id)
    if not project:
        return b""
    state = {"days": [_day_state(d) for d in project.days]}
    return zlib.compress(json.dumps(state).encode(), 6)


def apply(db: Session, project_id: int, blob: bytes) -> None:
    """Put the project back to a captured state, recreating or removing days."""
    if not blob:
        return
    state = json.loads(zlib.decompress(blob).decode())
    wanted = {d["id"]: d for d in state["days"]}

    existing = {d.id: d for d in db.query(Day).filter(Day.project_id == project_id).all()}

    # Days created since the snapshot go away; their connectors cascade.
    for day_id, day in existing.items():
        if day_id not in wanted:
            db.delete(day)

    for day_id, want in wanted.items():
        day = existing.get(day_id)
        if day is None:
            # Reuse the original id so anything holding a reference still resolves.
            day = Day(id=day_id, project_id=project_id)
            db.add(day)
        day.name = want["name"]
        day.order_index = want["order_index"]
        day.is_circular = want["is_circular"]
        day.is_locked = want["is_locked"]
        day.lock_start = want["lock_start"]
        day.lock_end = want["lock_end"]
        day.points = want["points"]
        day.source_points = want["source_points"]

    db.flush()

    # Connectors are small; rebuilding them wholesale avoids fiddly diffing.
    day_ids = list(wanted)
    if day_ids:
        for connector in db.query(Connector).filter(Connector.day_id.in_(day_ids)).all():
            db.delete(connector)
        db.flush()
        for want in wanted.values():
            for c in want["connectors"]:
                db.add(
                    Connector(
                        id=c["id"],
                        day_id=want["id"],
                        name=c["name"],
                        type=c["type"],
                        points=c["points"],
                    )
                )


def _stack(db: Session, project_id: int, kind: str):
    return (
        db.query(HistorySnapshot)
        .filter(HistorySnapshot.project_id == project_id, HistorySnapshot.kind == kind)
        .order_by(HistorySnapshot.id.desc())
    )


def record(db: Session, project_id: int, action: str) -> None:
    """Save the current state before an edit. Call this *before* mutating."""
    blob = capture(db, project_id)
    if not blob:
        return
    db.add(HistorySnapshot(project_id=project_id, kind="undo", action=action, state=blob))

    # A new edit makes any redo history unreachable.
    for entry in _stack(db, project_id, "redo").all():
        db.delete(entry)

    stale = _stack(db, project_id, "undo").offset(MAX_ENTRIES).all()
    for entry in stale:
        db.delete(entry)
    db.flush()


def _step(db: Session, project_id: int, from_kind: str, to_kind: str) -> str | None:
    entry = _stack(db, project_id, from_kind).first()
    if entry is None:
        return None

    # The current state becomes the way back.
    db.add(
        HistorySnapshot(
            project_id=project_id,
            kind=to_kind,
            action=entry.action,
            state=capture(db, project_id),
        )
    )
    apply(db, project_id, entry.state)
    action = entry.action
    db.delete(entry)
    db.commit()
    return action


def undo(db: Session, project_id: int) -> str | None:
    return _step(db, project_id, "undo", "redo")


def redo(db: Session, project_id: int) -> str | None:
    return _step(db, project_id, "redo", "undo")


def status(db: Session, project_id: int) -> dict:
    undo_entries = _stack(db, project_id, "undo").limit(1).all()
    redo_entries = _stack(db, project_id, "redo").limit(1).all()
    return {
        "can_undo": bool(undo_entries),
        "can_redo": bool(redo_entries),
        "undo_action": undo_entries[0].action if undo_entries else None,
        "redo_action": redo_entries[0].action if redo_entries else None,
        "undo_depth": _stack(db, project_id, "undo").count(),
        "redo_depth": _stack(db, project_id, "redo").count(),
    }
