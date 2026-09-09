"""Shared fixtures.

The tests exercise the pure route maths rather than the database, because that's
where the trip-breaking bugs have actually lived: a day silently losing 15 km, or
a loop's wrap join being skipped. Those are all expressible as invariants over
point lists.
"""

import sys
from pathlib import Path

import pytest

# The app is imported as `app.*` from the backend directory, matching the image.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ~100 m of latitude at the equator-ish spacing used throughout these tests.
STEP = 0.0009


def line(n: int, lat0: float = 51.0, lon: float = 1.0) -> list[dict]:
    """A straight north-running track of n points, roughly 100 m apart."""
    return [{"lat": lat0 + STEP * i, "lon": lon, "ele": None, "time": None} for i in range(n)]


def ring(n: int = 240) -> list[dict]:
    """A closed square loop of n points that returns exactly to its start."""
    per = n // 4
    pts, lat, lon = [], 51.0, 1.0
    for dlat, dlon in ((STEP, 0.0), (0.0, STEP), (-STEP, 0.0), (0.0, -STEP)):
        for _ in range(per):
            pts.append({"lat": lat, "lon": lon, "ele": None, "time": None})
            lat, lon = lat + dlat, lon + dlon
    pts.append(dict(pts[0]))  # close it
    return pts


def cut(points: list[dict], parts: int) -> list[list[dict]]:
    """Split into consecutive days that share one point at each join."""
    size = (len(points) - 1) // parts
    bounds = [i * size for i in range(parts)] + [len(points) - 1]
    return [[dict(p) for p in points[bounds[i] : bounds[i + 1] + 1]] for i in range(parts)]


@pytest.fixture
def loop_days() -> list[list[dict]]:
    """Four days covering a closed loop, sharing a point at every join."""
    return cut(ring(240), 4)
