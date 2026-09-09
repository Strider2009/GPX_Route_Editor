from .geo import cumulative_distance, elevation_gain_loss
from .models import Connector, Day, Project
from .route_ops import window_in_source


def day_stats(points: list[dict]) -> dict:
    ascent, descent = elevation_gain_loss(points)
    return {
        "point_count": len(points),
        "distance_m": cumulative_distance(points),
        "ascent_m": ascent,
        "descent_m": descent,
    }


def connector_schema(c: Connector) -> dict:
    return {
        "id": c.id,
        "day_id": c.day_id,
        "name": c.name,
        "type": c.type,
        "points": c.points or [],
    }


def day_summary(day: Day) -> dict:
    return {
        "id": day.id,
        "project_id": day.project_id,
        "name": day.name,
        "order_index": day.order_index,
        "is_circular": day.is_circular,
        "is_locked": day.is_locked,
        "lock_start": day.lock_start,
        "lock_end": day.lock_end,
        "stats": day_stats(day.points or []),
    }


def day_detail(day: Day) -> dict:
    data = day_summary(day)
    data["points"] = day.points or []
    # Only ship the wider route when it actually adds something, so untrimmed
    # days don't pay for a second copy of their points.
    source = day.source_points or []
    trimmed = bool(source) and len(source) > len(day.points or [])
    data["is_trimmed"] = trimmed
    data["source_points"] = source if trimmed else []
    # Where the visible route sits inside the wider one, so the client can talk
    # about both in the same index space.
    if trimmed:
        start, end = window_in_source(source, day.points or [])
    else:
        start, end = 0, max(0, len(day.points or []) - 1)
    data["source_start"] = start
    data["source_end"] = end
    data["connectors"] = [connector_schema(c) for c in day.connectors]
    return data


def project_summary(project: Project) -> dict:
    return {
        "id": project.id,
        "name": project.name,
        "source_filename": project.source_filename,
        "created_at": project.created_at,
        "day_count": len(project.days),
    }


def project_detail(project: Project) -> dict:
    data = project_summary(project)
    data["days"] = [day_summary(d) for d in sorted(project.days, key=lambda d: d.order_index)]
    return data
