"""Filling routes with heights, and measuring providers against recorded ones.

Pure functions over point lists, like route_ops: the routers own the database
and the undo history.
"""

import math
import time

from ..geo import cumulative_distance, elevation_gain_loss, haversine
from .providers import COORD_DP, Coord, ElevationError, ElevationProvider, Progress

# Enough to see how a provider tracks the road without spending a rate-limited
# provider's daily allowance on one comparison.
DEFAULT_COMPARE_SAMPLES = 300
# Compares run inside the request, so stay within one minute of Open-Meteo's
# budget; a bigger sample would sit waiting on its rate limit.
MAX_COMPARE_SAMPLES = 500


def _key(p: dict) -> Coord:
    return (round(p["lat"], COORD_DP), round(p["lon"], COORD_DP))


def coords_to_fill(point_lists: list[list[dict]], overwrite: bool = False) -> list[Coord]:
    """Each distinct location that needs a height, in route order."""
    wanted = (_key(p) for pts in point_lists for p in pts if overwrite or p.get("ele") is None)
    return list(dict.fromkeys(wanted))


def apply_heights(
    point_lists: list[list[dict]], heights: dict[Coord, float | None], overwrite: bool = False
) -> int:
    """Write looked-up heights into the points in place, matched by location.

    Matching by location rather than position means heights still land correctly
    on a route that was edited while they were being fetched. Without
    `overwrite` recorded heights are left alone. Returns how many points changed.
    """
    changed = 0
    for pts in point_lists:
        for p in pts:
            if not overwrite and p.get("ele") is not None:
                continue
            h = heights.get(_key(p))
            if h is not None:
                p["ele"] = round(h, 1)
                changed += 1
    return changed


def fill(
    point_lists: list[list[dict]],
    provider: ElevationProvider,
    overwrite: bool = False,
    progress: Progress | None = None,
) -> int:
    """Look up and write heights in one go. Returns how many points changed."""
    coords = coords_to_fill(point_lists, overwrite)
    if not coords:
        return 0
    heights = dict(zip(coords, provider.lookup(coords, progress), strict=True))
    return apply_heights(point_lists, heights, overwrite)


def _sample_indices(n: int, samples: int) -> list[int]:
    if n <= samples:
        return list(range(n))
    step = (n - 1) / (samples - 1)
    return sorted({round(k * step) for k in range(samples)})


def _stats(recorded: list[float | None], provided: list[float | None]) -> dict | None:
    """Differences provider minus recorded, over points both have a height for."""
    diffs = [
        p - r for r, p in zip(recorded, provided, strict=True) if r is not None and p is not None
    ]
    if not diffs:
        return None
    n = len(diffs)
    mean = sum(diffs) / n
    return {
        "compared": n,
        "bias_m": round(mean, 1),
        "mae_m": round(sum(abs(d) for d in diffs) / n, 1),
        "rmse_m": round(math.sqrt(sum(d * d for d in diffs) / n), 1),
        "max_abs_m": round(max(abs(d) for d in diffs), 1),
    }


def _ascent(lats_lons: list[dict], heights: list[float | None]) -> dict:
    ascent, descent = elevation_gain_loss(
        [
            {"lat": p["lat"], "lon": p["lon"], "ele": h}
            for p, h in zip(lats_lons, heights, strict=True)
        ]
    )
    return {"ascent_m": round(ascent), "descent_m": round(descent)}


def compare(
    points: list[dict],
    providers: list[ElevationProvider],
    samples: int = DEFAULT_COMPARE_SAMPLES,
) -> dict:
    """Look up the same evenly spaced points with each provider and score them.

    Ascent is summed over the sampled points for every series, the recorded one
    included, so the figures compare like with like - they'll read lower than
    the day's real total, which counts every point.
    """
    samples = max(2, min(samples, MAX_COMPARE_SAMPLES))
    idxs = _sample_indices(len(points), samples)
    picked = [points[i] for i in idxs]

    dists = [0.0]
    for a, b in zip(picked, picked[1:], strict=False):
        dists.append(dists[-1] + haversine(a, b))

    recorded = [p.get("ele") for p in picked]
    has_recorded = any(e is not None for e in recorded)

    results = []
    for provider in providers:
        entry = {**provider.info(), "error": None, "stats": None}
        start = time.monotonic()
        try:
            heights = provider.lookup([(p["lat"], p["lon"]) for p in picked])
        except ElevationError as e:
            entry["error"] = str(e)
            results.append(entry)
            continue
        entry["seconds"] = round(time.monotonic() - start, 1)
        entry["heights"] = [None if h is None else round(h, 1) for h in heights]
        entry["profile"] = _ascent(picked, heights)
        if has_recorded:
            entry["stats"] = _stats(recorded, heights)
        results.append(entry)

    return {
        "point_count": len(points),
        "distance_m": round(cumulative_distance(points)),
        "samples": [
            {"index": i, "d": round(d), "ele": e}
            for i, d, e in zip(idxs, dists, recorded, strict=True)
        ],
        "recorded": _ascent(picked, recorded) if has_recorded else None,
        "providers": results,
    }
