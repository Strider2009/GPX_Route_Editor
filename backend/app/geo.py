import math


def haversine(p1: dict, p2: dict) -> float:
    """Great-circle distance between two {lat, lon} points, in metres."""
    r = 6371000.0
    lat1, lon1 = math.radians(p1["lat"]), math.radians(p1["lon"])
    lat2, lon2 = math.radians(p2["lat"]), math.radians(p2["lon"])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def cumulative_distance(points: list[dict]) -> float:
    total = 0.0
    for i in range(1, len(points)):
        total += haversine(points[i - 1], points[i])
    return total


def _local_xy(lat: float, lon: float, lat0: float) -> tuple[float, float]:
    """Equirectangular projection to metres, accurate enough over a few km."""
    r = 6371000.0
    x = math.radians(lon) * r * math.cos(math.radians(lat0))
    y = math.radians(lat) * r
    return x, y


def _point_segment_distance(p, a, b) -> float:
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def distance_to_route(lat: float, lon: float, points: list[dict]) -> tuple[float, int]:
    """Shortest distance in metres from a point to a route polyline.

    Returns (distance_m, index_of_nearest_route_point).
    """
    if not points:
        return float("inf"), -1
    lat0 = points[len(points) // 2]["lat"]
    px, py = _local_xy(lat, lon, lat0)

    best = float("inf")
    best_idx = 0
    prev = _local_xy(points[0]["lat"], points[0]["lon"], lat0)
    # Distance to the first vertex, in case the route is a single point.
    best = math.hypot(px - prev[0], py - prev[1])

    for i in range(1, len(points)):
        cur = _local_xy(points[i]["lat"], points[i]["lon"], lat0)
        d = _point_segment_distance((px, py), prev, cur)
        if d < best:
            best = d
            # Attribute the hit to whichever end of the segment is closer.
            d_prev = math.hypot(px - prev[0], py - prev[1])
            d_cur = math.hypot(px - cur[0], py - cur[1])
            best_idx = i - 1 if d_prev <= d_cur else i
        prev = cur
    return best, best_idx


def elevation_gain_loss(points: list[dict]) -> tuple[float, float]:
    ascent = descent = 0.0
    for i in range(1, len(points)):
        e0, e1 = points[i - 1].get("ele"), points[i].get("ele")
        if e0 is None or e1 is None:
            continue
        delta = e1 - e0
        if delta > 0:
            ascent += delta
        else:
            descent += -delta
    return ascent, descent
