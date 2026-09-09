"""Pure point-list operations behind the route editing features.

Anything that mutates a Day's core `points` goes through here so the locking
rule ("locked days can't have their core route changed") lives in one place.
"""

from fastapi import HTTPException

from .geo import cumulative_distance, haversine  # noqa: F401 (re-exported)
from .models import Day

CIRCULAR_THRESHOLD_M = 75.0


def require_unlocked(day: Day) -> None:
    if day.is_locked:
        raise HTTPException(
            409, f"Day '{day.name}' is locked. Unlock it before changing the core route."
        )


def detect_circular(points: list[dict], threshold_m: float = CIRCULAR_THRESHOLD_M) -> bool:
    """Heuristic used at import time: is the end close to the start?"""
    if len(points) < 3:
        return False
    return haversine(points[0], points[-1]) <= threshold_m


def rotate_to_start(points: list[dict], index: int) -> list[dict]:
    """Make `points[index]` the new start/end of a closed loop."""
    if not points:
        return points
    index = index % len(points)
    rotated = points[index:] + points[:index]
    if rotated[0] != rotated[-1]:
        rotated = rotated + [dict(rotated[0])]
    return rotated


def trim(points: list[dict], start_index: int, end_index: int) -> list[dict]:
    """Keep only [start_index, end_index], reversing if start is after end."""
    lo, hi = min(start_index, end_index), max(start_index, end_index)
    subset = points[lo : hi + 1]
    if start_index > end_index:
        subset = list(reversed(subset))
    return subset


def reverse(points: list[dict]) -> list[dict]:
    return list(reversed(points))


def split(points: list[dict], split_indices: list[int]) -> list[list[dict]]:
    """Cut points into contiguous chunks at the given interior indices."""
    n = len(points)
    idxs = sorted({i for i in split_indices if 0 < i < n - 1})
    bounds = [0] + idxs + [n - 1]
    return [points[a : b + 1] for a, b in zip(bounds, bounds[1:], strict=False)]


def even_split_indices(points: list[dict], parts: int, climb_weight: float = 0.0) -> list[int]:
    """Indices that cut a route into `parts` roughly equal pieces.

    With climb_weight > 0 the "effort" of a segment counts ascent as well as
    distance, so hilly sections make for shorter days. A weight of 1.0 treats
    100 m of climbing as costing the same as 1 km of flat.
    """
    if parts < 2 or len(points) < parts + 1:
        return []

    # Running effort along the route.
    effort = [0.0]
    for i in range(1, len(points)):
        step = haversine(points[i - 1], points[i])
        if climb_weight:
            e0, e1 = points[i - 1].get("ele"), points[i].get("ele")
            if e0 is not None and e1 is not None and e1 > e0:
                step += (e1 - e0) * 10.0 * climb_weight
        effort.append(effort[-1] + step)

    total = effort[-1]
    if total <= 0:
        return []

    cuts: list[int] = []
    for part in range(1, parts):
        target = total * part / parts
        # First index at or past the target effort.
        lo, hi = 0, len(effort) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if effort[mid] < target:
                lo = mid + 1
            else:
                hi = mid
        idx = min(max(lo, 1), len(points) - 2)
        if idx not in cuts:
            cuts.append(idx)
    return sorted(cuts)


def nearest_index(points: list[dict], probe: dict) -> int:
    """Index of the point closest to `probe`."""
    best_i, best_d = 0, float("inf")
    for i, p in enumerate(points):
        d = haversine(p, probe)
        if d < best_d:
            best_i, best_d = i, d
    return best_i


def window_in_source(source: list[dict], window: list[dict]) -> tuple[int, int]:
    """Where `window` sits inside `source`.

    Exact when the window really is a slice of it; otherwise the nearest points,
    which is what's needed when the shadow comes from a separately uploaded route
    that only roughly follows the same ground.
    """
    if not source or not window:
        return 0, max(0, len(window) - 1)
    exact = offset_in_source(source, window)
    if exact is not None:
        return exact, exact + len(window) - 1
    start = nearest_index(source, window[0])
    end = nearest_index(source, window[-1])
    return (start, end) if start <= end else (end, start)


def offset_in_source(source: list[dict], window: list[dict]) -> int | None:
    """Where `window` starts inside `source`, or None if it isn't a slice of it.

    Matched on coordinates rather than identity, since the points travel through
    JSON and come back as fresh dicts.
    """
    if not source or not window or len(window) > len(source):
        return None

    def key(p):
        return (p.get("lat"), p.get("lon"))

    first = key(window[0])
    last = key(window[-1])
    span = len(window) - 1
    for i, point in enumerate(source):
        if key(point) == first and i + span < len(source) and key(source[i + span]) == last:
            return i
    return None


MIN_DAY_POINTS = 2


def _walk(points: list[dict], indices, distance_m: float) -> tuple[int, float]:
    """Step along `indices` until `distance_m` is covered. Returns (steps, actual)."""
    travelled = 0.0
    steps = 0
    prev = indices[0]
    for idx in indices[1:]:
        leg = haversine(points[prev], points[idx])
        if travelled + leg > distance_m:
            break
        travelled += leg
        steps += 1
        prev = idx
    return steps, travelled


def boundary_range(a: list[dict], b: list[dict]) -> tuple[float, float]:
    """How far the shared boundary could move back and forward, in metres."""
    back = cumulative_distance(a[: len(a) - MIN_DAY_POINTS + 1]) if len(a) > MIN_DAY_POINTS else 0.0
    forward = (
        cumulative_distance(b[: len(b) - MIN_DAY_POINTS + 1]) if len(b) > MIN_DAY_POINTS else 0.0
    )
    return back, forward


def move_boundary(
    a: list[dict], b: list[dict], delta_m: float
) -> tuple[list[dict], list[dict], float]:
    """Slide the point shared by two consecutive days along the route.

    Positive delta lengthens the first day and shortens the second. The two days
    keep sharing exactly one point, which is what makes them a continuous route.
    Returns (new_a, new_b, distance actually moved).
    """
    if not a or not b or not delta_m:
        return a, b, 0.0

    if delta_m > 0:
        limit = len(b) - MIN_DAY_POINTS
        if limit <= 0:
            return a, b, 0.0
        steps, moved = _walk(b, range(0, limit + 1), delta_m)
        if steps <= 0:
            return a, b, 0.0
        return a + [dict(p) for p in b[1 : steps + 1]], b[steps:], moved

    limit = len(a) - MIN_DAY_POINTS
    if limit <= 0:
        return a, b, 0.0
    steps, moved = _walk(a, range(len(a) - 1, len(a) - limit - 2, -1), -delta_m)
    if steps <= 0:
        return a, b, 0.0
    cut = len(a) - 1 - steps
    return a[: cut + 1], [dict(p) for p in a[cut:]] + b[1:], -moved


def merge(points_a: list[dict], points_b: list[dict]) -> list[dict]:
    if points_a and points_b and points_a[-1] == points_b[0]:
        return points_a + points_b[1:]
    return points_a + points_b
