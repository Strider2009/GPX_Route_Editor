from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..elevation import jobs
from ..elevation.providers import PROVIDERS, ElevationError, default_provider_id, get_provider
from ..elevation.service import DEFAULT_COMPARE_SAMPLES, MAX_COMPARE_SAMPLES, compare
from .days import get_day_or_404
from .projects import get_project_or_404

router = APIRouter(tags=["elevation"])


class FillRequest(BaseModel):
    provider: str | None = None
    # Replace heights the route already has, not just the gaps.
    overwrite: bool = False


@router.get("/elevation/providers")
def list_providers():
    default = default_provider_id()
    return [{**p.info(), "default": p.id == default} for p in PROVIDERS.values()]


@router.post("/projects/{project_id}/elevation", status_code=202)
def fill_project_elevation(project_id: int, payload: FillRequest, db: Session = Depends(get_db)):
    """Start giving every day's points a height from a provider, as one undoable step.

    Returns a job to poll: a rate-limited provider can take minutes over a long trip.
    """
    project = get_project_or_404(db, project_id)
    try:
        provider = get_provider(payload.provider)
    except ElevationError as e:
        raise HTTPException(400, str(e)) from e
    return jobs.start(project, provider, payload.overwrite).view()


@router.get("/elevation/jobs/{job_id}")
def fill_job_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "No such elevation job - the server may have restarted")
    return job.view()


@router.get("/days/{day_id}/elevation/compare")
def compare_day_elevation(
    day_id: int,
    providers: list[str] = Query(default_factory=list),
    samples: int = Query(DEFAULT_COMPARE_SAMPLES, ge=2, le=MAX_COMPARE_SAMPLES),
    db: Session = Depends(get_db),
):
    """Each provider's heights for the same sampled points, scored against the recorded ones."""
    day = get_day_or_404(db, day_id)
    points = day.points or []
    if len(points) < 2:
        raise HTTPException(400, "This day has too few points to compare")
    try:
        chosen = [get_provider(pid) for pid in (providers or list(PROVIDERS))]
    except ElevationError as e:
        raise HTTPException(400, str(e)) from e
    return compare(points, chosen, samples)
