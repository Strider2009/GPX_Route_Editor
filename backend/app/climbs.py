"""Finding the climbs in a route from its own elevation profile.

Deliberately computed rather than looked up: a climb database only knows about
climbs somebody bothered to create an entry for, whereas the route's own profile
covers every metre of it and describes the climb you will actually ride rather
than an arbitrary section of it.

GPS elevation is noisy - a metre or two of jitter per point is normal - so the
profile is smoothed before anything is measured. Without that, a flat road
"gains" tens of metres over a few kilometres and every ride looks lumpy.
"""

from .geo import haversine

# A climb has to be at least this much to be worth mentioning in a briefing.
MIN_GAIN_M = 20.0
MIN_LENGTH_M = 300.0
MIN_AVG_GRADIENT = 2.5
# Below this a "descent" is just leftover jitter, not the end of a climb.
NOISE_M = 3.0
# A false flat partway up is part of the climb; a real dip between two rollers
# is not. Both tests must pass to merge, which is what separates the two: 2 m
# after a 100 m climb is a false flat, 12 m after 35 m is a separate roller.
MAX_DIP_M = 8.0
DIP_FRACTION = 0.2
# Wide enough to kill per-point GPS jitter, narrow enough to leave real terrain
# alone. At 5 it flattened the 12 m dips between rollers to under the merge
# threshold, so a rolling day collapsed into one shallow segment and reported
# no climbs at all.
SMOOTHING_WINDOW = 3

# length_m x average gradient %, the usual convention for categorising climbs.
CATEGORY_BANDS = [
    (128_000, "HC"),
    (64_000, "1"),
    (32_000, "2"),
    (16_000, "3"),
    (8_000, "4"),
]


def _filled_elevations(points: list[dict]) -> list[float] | None:
    """Raw elevations with gaps carried forward, or None if the route has none.

    Gaps are filled rather than dropped so indices still line up with the route.
    """
    raw = [p.get("ele") for p in points]
    if not any(e is not None for e in raw):
        return None

    filled: list[float] = []
    last = next((e for e in raw if e is not None), 0.0)
    for e in raw:
        if e is not None:
            last = float(e)
        filled.append(last)
    return filled


def _smooth(filled: list[float]) -> list[float]:
    half = SMOOTHING_WINDOW // 2
    out = []
    for i in range(len(filled)):
        lo = max(0, i - half)
        hi = min(len(filled), i + half + 1)
        out.append(sum(filled[lo:hi]) / (hi - lo))
    return out


def _smoothed_elevations(points: list[dict]) -> list[float] | None:
    filled = _filled_elevations(points)
    return None if filled is None else _smooth(filled)


def categorise(length_m: float, avg_gradient: float) -> str | None:
    score = length_m * avg_gradient
    for threshold, label in CATEGORY_BANDS:
        if score >= threshold:
            return label
    return None


def _measure(points: list[dict], eles: list[float], start: int, end: int) -> dict | None:
    length = 0.0
    for i in range(start, end):
        length += haversine(points[i], points[i + 1])
    gain = eles[end] - eles[start]
    if gain < MIN_GAIN_M or length < MIN_LENGTH_M:
        return None
    avg = 100.0 * gain / length if length else 0.0
    if avg < MIN_AVG_GRADIENT:
        return None

    # Steepest sustained 100 m, which is what actually hurts.
    steepest = 0.0
    j = start
    for i in range(start, end):
        run = 0.0
        j = i
        while j < end and run < 100.0:
            run += haversine(points[j], points[j + 1])
            j += 1
        if run >= 50.0:
            steepest = max(steepest, 100.0 * (eles[j] - eles[i]) / run)

    return {
        "start_index": start,
        "end_index": end,
        "length_m": round(length, 1),
        "gain_m": round(gain, 1),
        "avg_gradient": round(avg, 1),
        "max_gradient": round(steepest, 1),
        "category": categorise(length, avg),
        "start_ele_m": round(eles[start], 1),
        "top_ele_m": round(eles[end], 1),
    }


def _rising_segments(eles: list[float]) -> list[tuple[int, int]]:
    """Every (start, peak) where the ground goes up, ignoring jitter.

    Deliberately eager - it splits on any real descent. Deciding which of these
    are separate climbs and which are one climb with a false flat in it is the
    merge step's job, because that decision needs both sides of the dip.
    """
    segments: list[tuple[int, int]] = []
    start = None
    peak = None

    for i in range(1, len(eles)):
        if eles[i] > eles[i - 1]:
            if start is None:
                start = i - 1
            peak = i
        elif start is not None and eles[peak] - eles[i] > NOISE_M:
            segments.append((start, peak))
            start = None
            peak = None

    if start is not None and peak is not None and peak > start:
        segments.append((start, peak))
    return segments


def _merge_false_flats(
    eles: list[float], raw: list[float], segments: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    """Join segments separated by a dip too small to count as a descent.

    The dip is measured on the raw profile, not the smoothed one. Smoothing
    exists to steady the gradient maths, but it also shaves a third off a short
    dip - a real 12 m drop between two rollers came out as 8 m, landed exactly
    on the threshold, and merged a whole rolling day into one shallow segment.
    """
    if not segments:
        return []

    merged = [segments[0]]
    for start, peak in segments[1:]:
        prev_start, prev_peak = merged[-1]
        # Segment indices come from the smoothed profile, whose peak sits up to
        # half a window past the raw one, so reading raw[prev_peak] directly
        # starts partway down the descent. Straddle that offset on both sides.
        half = SMOOTHING_WINDOW // 2
        crest = max(raw[max(0, prev_peak - half) : prev_peak + 1])
        trough = min(raw[prev_peak : min(len(raw), start + 1 + half)])
        dip = crest - trough
        combined = (eles[prev_peak] - eles[prev_start]) + (eles[peak] - eles[start])
        if dip <= MAX_DIP_M and dip <= DIP_FRACTION * max(combined, 1.0):
            merged[-1] = (prev_start, peak)
        else:
            merged.append((start, peak))
    return merged


def find_climbs(points: list[dict]) -> list[dict]:
    """Every sustained ascent worth naming, in route order."""
    if len(points) < 3:
        return []
    raw = _filled_elevations(points)
    if raw is None:
        return []
    eles = _smooth(raw)

    climbs = []
    for start, peak in _merge_false_flats(eles, raw, _rising_segments(eles)):
        climb = _measure(points, eles, start, peak)
        if climb:
            climbs.append(climb)
    return climbs


def profile_summary(points: list[dict]) -> dict:
    """Overall shape of the day, for the top of a briefing."""
    eles = _smoothed_elevations(points)
    if eles is None:
        return {"has_elevation": False}
    return {
        "has_elevation": True,
        "min_ele_m": round(min(eles), 1),
        "max_ele_m": round(max(eles), 1),
        "start_ele_m": round(eles[0], 1),
        "end_ele_m": round(eles[-1], 1),
    }
