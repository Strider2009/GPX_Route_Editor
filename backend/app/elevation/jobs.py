"""Filling a project's heights in the background.

A rate-limited provider can take minutes over a long trip - Open-Meteo's free
tier allows about 600 points a minute - which is far longer than a request
should be held open. So a fill runs on its own thread and the page polls it.

Jobs live in memory: a restart loses a running fill, but nothing is written
until the end, so it loses nothing else and can simply be run again.
"""

import copy
import logging
import threading
import uuid
from dataclasses import asdict, dataclass, field

from .. import history
from ..database import SessionLocal
from ..models import Project
from .providers import ElevationError, ElevationProvider
from .service import apply_heights, coords_to_fill

logger = logging.getLogger(__name__)


@dataclass
class FillJob:
    project_id: int
    # SQLite reuses the ids of deleted rows, so the id alone can't say a project
    # is the one this job was started for.
    project_created_at: str
    provider: str
    provider_label: str
    overwrite: bool
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: str = "running"  # running | done | error
    done: int = 0
    total: int = 0
    filled: int = 0
    error: str | None = None

    def view(self) -> dict:
        return asdict(self)


_jobs: dict[str, FillJob] = {}
_lock = threading.Lock()


def get(job_id: str) -> FillJob | None:
    return _jobs.get(job_id)


def _is_same(job: FillJob, project: Project | None) -> bool:
    return project is not None and str(project.created_at) == job.project_created_at


def start(project: Project, provider: ElevationProvider, overwrite: bool) -> FillJob:
    """Start a fill, or hand back the one already running for this project."""
    with _lock:
        for job in _jobs.values():
            if job.status == "running" and job.project_id == project.id and _is_same(job, project):
                return job
        job = FillJob(project.id, str(project.created_at), provider.id, provider.label, overwrite)
        _jobs[job.id] = job
    threading.Thread(target=_run, args=(job, provider), daemon=True).start()
    return job


def _point_lists(project: Project) -> list[list[dict]]:
    # Source points too, so heights survive un-trimming a day.
    return [pts for day in project.days for pts in (day.points or [], day.source_points or [])]


def _run(job: FillJob, provider: ElevationProvider) -> None:
    try:
        with SessionLocal() as db:
            project = db.get(Project, job.project_id)
            if not _is_same(job, project):
                raise ElevationError("The project no longer exists")
            coords = coords_to_fill(_point_lists(project), job.overwrite)
        # The session is closed while we wait on the provider, so no transaction
        # is held open for minutes.
        job.total = len(coords)

        def progress(done: int, _total: int) -> None:
            job.done = done

        heights = (
            dict(zip(coords, provider.lookup(coords, progress), strict=True)) if coords else {}
        )

        with SessionLocal() as db:
            project = db.get(Project, job.project_id)
            if not _is_same(job, project):
                raise ElevationError("The project was deleted while its heights were being fetched")
            # Applied to the route as it is now, which may have been edited meanwhile.
            # Copies, because the JSON columns only notice a reassignment.
            edited = [
                (day, copy.deepcopy(day.points or []), copy.deepcopy(day.source_points or []))
                for day in project.days
            ]
            # Counted on the route as shown; the source copies get the same heights.
            filled = apply_heights([p for _, p, _ in edited], heights, job.overwrite)
            apply_heights([s for _, _, s in edited], heights, job.overwrite)
            if filled:
                history.record(db, job.project_id, f"Fill elevation ({provider.label})")
                for day, points, source in edited:
                    day.points = points
                    day.source_points = source
                db.commit()
        job.filled = filled
        job.status = "done"
    except ElevationError as e:
        job.error = str(e)
        job.status = "error"
    except Exception:
        logger.exception("Elevation fill failed for project %s", job.project_id)
        job.error = "Filling elevation failed unexpectedly - see the server log"
        job.status = "error"
