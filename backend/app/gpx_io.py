from datetime import datetime

import gpxpy
import gpxpy.gpx


def parse_gpx(data: bytes) -> list[dict]:
    """Parse raw GPX bytes into a list of {name, points} tracks.

    Falls back to <rte> routes if the file has no <trk> tracks.
    """
    text = data.decode("utf-8", errors="replace")
    gpx = gpxpy.parse(text)

    tracks: list[dict] = []
    for trk in gpx.tracks:
        points = []
        for seg in trk.segments:
            for pt in seg.points:
                points.append(
                    {
                        "lat": pt.latitude,
                        "lon": pt.longitude,
                        "ele": pt.elevation,
                        "time": pt.time.isoformat() if pt.time else None,
                    }
                )
        if points:
            tracks.append({"name": trk.name or "Imported track", "points": points})

    if not tracks:
        for rte in gpx.routes:
            points = [
                {"lat": p.latitude, "lon": p.longitude, "ele": p.elevation, "time": None}
                for p in rte.points
            ]
            if points:
                tracks.append({"name": rte.name or "Imported route", "points": points})

    if not tracks:
        raise ValueError("No tracks or routes with points were found")

    return tracks


def _parse_time(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def build_gpx(name: str, segments: list[tuple[str, list[dict]]]) -> bytes:
    """Build a GPX file where each (name, points) pair becomes its own <trk>."""
    gpx = gpxpy.gpx.GPX()
    gpx.name = name
    gpx.creator = "GPX Route Editor"

    for seg_name, points in segments:
        if not points:
            continue
        track = gpxpy.gpx.GPXTrack(name=seg_name)
        segment = gpxpy.gpx.GPXTrackSegment()
        for p in points:
            segment.points.append(
                gpxpy.gpx.GPXTrackPoint(
                    latitude=p["lat"],
                    longitude=p["lon"],
                    elevation=p.get("ele"),
                    time=_parse_time(p.get("time")),
                )
            )
        track.segments.append(segment)
        gpx.tracks.append(track)

    return gpx.to_xml().encode("utf-8")


def day_export_segments(day, include_connectors: bool = True) -> list[tuple[str, list[dict]]]:
    """Build the ordered (name, points) segments for exporting a single day.

    Order: start_access connector(s) -> core route -> end_access connector(s) -> spurs.
    """
    segments: list[tuple[str, list[dict]]] = []
    if include_connectors:
        for c in day.connectors:
            if c.type == "start_access" and c.points:
                segments.append((c.name, c.points))
    segments.append((day.name, day.points or []))
    if include_connectors:
        for c in day.connectors:
            if c.type == "end_access" and c.points:
                segments.append((c.name, c.points))
        for c in day.connectors:
            if c.type == "spur" and c.points:
                segments.append((c.name, c.points))
    return segments
