import io
import zipfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import history
from ..database import get_db
from ..gpx_io import build_gpx, day_export_segments, parse_gpx
from ..models import Day, Project
from ..route_ops import detect_circular
from ..schemas import ReorderRequest
from ..serializers import project_detail, project_summary
from ..util import slugify

router = APIRouter(tags=["projects"])


def get_project_or_404(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@router.post("/projects/import")
async def import_project(
    files: list[UploadFile] = File(...),
    name: str | None = Form(None),
    db: Session = Depends(get_db),
):
    if not files:
        raise HTTPException(400, "No files uploaded")

    default_name = (files[0].filename or "Imported project").rsplit(".", 1)[0]
    project = Project(
        name=name or default_name,
        source_filename=", ".join(f.filename for f in files if f.filename),
    )
    db.add(project)
    db.flush()

    order = 0
    total_tracks = 0
    for f in files:
        data = await f.read()
        try:
            tracks = parse_gpx(data)
        except Exception as exc:
            db.rollback()
            raise HTTPException(400, f"Could not parse '{f.filename}': {exc}") from exc
        for t in tracks:
            day = Day(
                project_id=project.id,
                name=t["name"],
                order_index=order,
                is_circular=detect_circular(t["points"]),
                is_locked=False,
                points=t["points"],
                source_points=list(t["points"]),
            )
            db.add(day)
            order += 1
            total_tracks += 1

    if total_tracks == 0:
        db.rollback()
        raise HTTPException(400, "No tracks found in the uploaded file(s)")

    db.commit()
    db.refresh(project)
    return project_detail(project)


@router.post("/projects/{project_id}/import")
async def add_routes_to_project(
    project_id: int,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """Append more GPX files to an existing project as extra days."""
    project = get_project_or_404(db, project_id)
    history.record(db, project_id, "Add routes")
    order = max((d.order_index for d in project.days), default=-1) + 1

    added = 0
    for f in files:
        data = await f.read()
        try:
            tracks = parse_gpx(data)
        except Exception as exc:
            db.rollback()
            raise HTTPException(400, f"Could not parse '{f.filename}': {exc}") from exc
        for t in tracks:
            db.add(
                Day(
                    project_id=project.id,
                    name=t["name"],
                    order_index=order,
                    is_circular=detect_circular(t["points"]),
                    is_locked=False,
                    points=t["points"],
                    source_points=list(t["points"]),
                )
            )
            order += 1
            added += 1

    if added == 0:
        db.rollback()
        raise HTTPException(400, "No tracks found in the uploaded file(s)")

    db.commit()
    db.refresh(project)
    return project_detail(project)


@router.post("/projects/{project_id}/days/reorder")
def reorder_days(project_id: int, payload: ReorderRequest, db: Session = Depends(get_db)):
    """Set the whole day order in one go.

    Renumbering everything at once avoids the half-applied states you get from
    swapping pairs, where two days can briefly share an order_index.
    """
    project = get_project_or_404(db, project_id)
    by_id = {d.id: d for d in project.days}

    if set(payload.day_ids) != set(by_id):
        raise HTTPException(400, "The id list must name every day in this project exactly once")

    history.record(db, project_id, "Reorder days")

    for position, day_id in enumerate(payload.day_ids):
        by_id[day_id].order_index = position

    db.commit()
    db.refresh(project)
    return project_detail(project)


@router.get("/projects/{project_id}/history")
def project_history(project_id: int, db: Session = Depends(get_db)):
    get_project_or_404(db, project_id)
    return history.status(db, project_id)


@router.post("/projects/{project_id}/undo")
def undo_change(project_id: int, db: Session = Depends(get_db)):
    get_project_or_404(db, project_id)
    action = history.undo(db, project_id)
    if action is None:
        raise HTTPException(409, "Nothing to undo")
    return {"undone": action, **history.status(db, project_id)}


@router.post("/projects/{project_id}/redo")
def redo_change(project_id: int, db: Session = Depends(get_db)):
    get_project_or_404(db, project_id)
    action = history.redo(db, project_id)
    if action is None:
        raise HTTPException(409, "Nothing to redo")
    return {"redone": action, **history.status(db, project_id)}


@router.get("/projects/{project_id}/geometry")
def project_geometry(
    project_id: int,
    max_points: int = Query(900, ge=50, le=20000, description="Per day, for drawing"),
    db: Session = Depends(get_db),
):
    """Every day's line, thinned for drawing but carrying real point indices.

    Used to show the rest of the trip behind the day being edited. Each point is
    [lat, lon, index] so a click on the thinned line still maps back to the exact
    point in that day's route.
    """
    project = get_project_or_404(db, project_id)
    days = sorted(project.days, key=lambda d: d.order_index)

    out = []
    for day in days:
        points = day.points or []
        if not points:
            continue
        step = max(1, len(points) // max_points)
        thinned = [[points[i]["lat"], points[i]["lon"], i] for i in range(0, len(points), step)]
        last = len(points) - 1
        if thinned[-1][2] != last:
            thinned.append([points[last]["lat"], points[last]["lon"], last])
        out.append(
            {
                "day_id": day.id,
                "name": day.name,
                "order_index": day.order_index,
                "point_count": len(points),
                "is_locked": day.is_locked,
                "points": thinned,
            }
        )

    from .boundaries import is_loop as _is_loop

    return {"project_id": project_id, "days": out, "is_loop": _is_loop(days)}


@router.get("/projects")
def list_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    return [project_summary(p) for p in projects]


@router.get("/projects/{project_id}")
def get_project(project_id: int, db: Session = Depends(get_db)):
    return project_detail(get_project_or_404(db, project_id))


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = get_project_or_404(db, project_id)
    db.delete(project)
    db.commit()


@router.get("/projects/{project_id}/export")
def export_project(project_id: int, mode: str = "combined", db: Session = Depends(get_db)):
    project = get_project_or_404(db, project_id)
    days_sorted = sorted(project.days, key=lambda d: d.order_index)

    if mode == "zip":
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for day in days_sorted:
                xml = build_gpx(day.name, day_export_segments(day, include_connectors=True))
                zf.writestr(f"{slugify(day.name)}.gpx", xml)
        buf.seek(0)
        return Response(
            content=buf.read(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{slugify(project.name)}.zip"'},
        )

    segments = [(day.name, day.points or []) for day in days_sorted]
    xml = build_gpx(project.name, segments)
    return Response(
        content=xml,
        media_type="application/gpx+xml",
        headers={"Content-Disposition": f'attachment; filename="{slugify(project.name)}.gpx"'},
    )
