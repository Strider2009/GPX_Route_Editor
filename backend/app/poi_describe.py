"""Giving imported waypoints a name worth reading.

Route planners export their markers as bare <wpt>s called "Waypoint", which on a
head unit is no help at all. What a rider actually wants to know is where the
marker is: which junction, which town, how far into the day. All of that comes
from the route itself plus OpenStreetMap, so it needs no key and costs one
Overpass query per batch of waypoints.

The pure part - choosing a name and writing the notes from what was found - is
kept separate from the fetch so it can be tested without a network.
"""

import re

from . import overpass_fetch
from .geo import distance_to_route, haversine

# Names a planner gives a marker when nobody typed one. Anything else was
# chosen by a person and is left alone.
GENERIC = re.compile(
    r"^\s*(|waypoint|wpt|wp|via|point|poi|marker|pin|untitled|unnamed|"
    r"(waypoint|wpt|wp|point|poi|marker|pin)[\s#_-]*\d+|\d+)\s*$",
    re.IGNORECASE,
)

ROAD_RADIUS_M = 25
FEATURE_RADIUS_M = 80
# A landmark this close is what the marker is *for*, rather than just nearby.
FEATURE_IS_THE_POINT_M = 30
# Keeps each query comfortably small for a donated server.
BATCH = 20

# The named things worth mentioning, by tag. Anything not listed - post boxes,
# benches, artwork, police stations - is real but tells a rider nothing.
FEATURES: dict[str, set[str]] = {
    "amenity": {
        "cafe",
        "pub",
        "restaurant",
        "fast_food",
        "bar",
        "drinking_water",
        "toilets",
        "fuel",
        "pharmacy",
        "place_of_worship",
        "bicycle_repair_station",
        "ferry_terminal",
    },
    "shop": {"convenience", "supermarket", "bakery", "bicycle", "coffee", "farm"},
    "tourism": {
        "attraction",
        "museum",
        "viewpoint",
        "hotel",
        "guest_house",
        "hostel",
        "camp_site",
        "picnic_site",
        "castle",
    },
    "historic": {
        "castle",
        "monument",
        "archaeological_site",
        "ruins",
        "city_gate",
        "fort",
        "manor",
        "abbey",
        "church",
        "windmill",
        "milestone",
    },
    "natural": {"peak", "saddle", "spring", "beach", "cave_entrance"},
    "leisure": {"park", "nature_reserve"},
    "railway": {"station", "halt"},
    "man_made": {"bridge", "lighthouse", "windmill", "watermill"},
}

# Beyond this a marker is not really on the day at all - typically one that was
# attached at import and the day was later split or trimmed away from it.
ON_ROUTE_M = 1000

# How close counts as "in" a settlement rather than "near" it.
PLACE_IN_M = {"city": 4000, "town": 2000, "village": 800, "hamlet": 300}
PLACE_NEAR_M = 4000


def is_generic(name: str | None) -> bool:
    return bool(GENERIC.match(name or ""))


def build_query(pois: list[dict]) -> str:
    clauses = []
    for p in pois:
        at = f"{p['lat']:.6f},{p['lon']:.6f}"
        clauses.append(f'  way["highway"](around:{ROAD_RADIUS_M},{at});')
        for key in FEATURES:
            clauses.append(f'  nwr["{key}"]["name"](around:{FEATURE_RADIUS_M},{at});')
    body = "\n".join(clauses)
    # geom rather than center: a road's centre can be a mile from the junction.
    return f"[out:json][timeout:40];\n(\n{body}\n);\nout tags geom;"


def fetch(pois: list[dict]) -> list[dict]:
    """Every road and named feature near any of the waypoints, deduplicated."""
    seen: set[str] = set()
    out = []
    for i in range(0, len(pois), BATCH):
        payload = overpass_fetch._post(build_query(pois[i : i + BATCH]))
        for el in payload.get("elements", []):
            key = f"{el.get('type')}/{el.get('id')}"
            if key not in seen:
                seen.add(key)
                out.append(el)
    return out


def _kind(tags: dict) -> str | None:
    for key, values in FEATURES.items():
        value = tags.get(key)
        if value in values:
            return value.replace("_", " ")
    return None


def _distance(lat: float, lon: float, el: dict) -> float | None:
    geom = el.get("geometry")
    if geom:
        # A way's outline: distance to its nearest edge, not to its middle.
        return distance_to_route(lat, lon, [g for g in geom if g])[0]
    if el.get("lat") is not None:
        return haversine({"lat": lat, "lon": lon}, el)
    # Relations come back without usable geometry, and are mostly huge things
    # like long-distance paths that would match every waypoint on them anyway.
    return None


def _road_label(tags: dict) -> str | None:
    name, ref = tags.get("name"), tags.get("ref")
    if name and ref:
        return f"{name} ({ref})"
    return name or ref


def nearby(lat: float, lon: float, elements: list[dict]) -> tuple[list[str], list[dict]]:
    """The roads at a point, and the named features around it, nearest first."""
    roads: list[tuple[float, str]] = []
    features: list[dict] = []
    for el in elements:
        tags = el.get("tags") or {}
        if "highway" in tags and el.get("type") == "way":
            label = _road_label(tags)
            if not label:
                continue
            d = _distance(lat, lon, el)
            if d is not None and d <= ROAD_RADIUS_M:
                roads.append((d, label))
            continue
        kind = _kind(tags)
        if not kind or not tags.get("name"):
            continue
        d = _distance(lat, lon, el)
        if d is not None and d <= FEATURE_RADIUS_M:
            features.append({"name": tags["name"], "kind": kind, "distance_m": round(d)})

    # A road is split into many ways; name it once, at its nearest.
    labels: list[str] = []
    for _, label in sorted(roads):
        if label not in labels:
            labels.append(label)

    features.sort(key=lambda f: f["distance_m"])
    unique: list[dict] = []
    for f in features:
        if all(f["name"] != u["name"] for u in unique):
            unique.append(f)
    return labels, unique


def settlement(lat: float, lon: float, places: list[dict]) -> tuple[dict, bool] | None:
    """The nearest settlement, and whether the point is in it rather than near it."""
    best = None
    for p in places:
        d = haversine({"lat": lat, "lon": lon}, p)
        inside = d <= PLACE_IN_M.get(p["place"], 0)
        # Being inside a town beats being nearer to a hamlet out beyond it.
        score = (not inside, p["rank"] if inside else 0, d)
        if d <= PLACE_NEAR_M and (best is None or score < best[0]):
            best = (score, p, inside)
    return (best[1], best[2]) if best else None


def _short(label: str) -> str:
    """A road without its ref, for the name line where space is short."""
    return re.sub(r"\s*\([^)]*\)$", "", label)


def describe(
    poi: dict,
    points: list[dict],
    cumulative_m: list[float],
    elements: list[dict],
    places: list[dict],
) -> dict:
    """A name, notes and height for one waypoint, from what lies around it."""
    lat, lon = poi["lat"], poi["lon"]
    roads, features = nearby(lat, lon, elements)
    # A named cafe would otherwise list itself as the thing nearby.
    features = [f for f in features if f["name"] != poi.get("name")]
    town = settlement(lat, lon, places)

    off_m, idx = distance_to_route(lat, lon, points) if points else (None, -1)
    at_km = round(cumulative_m[idx] / 1000.0, 1) if idx >= 0 else None
    on_route = off_m is not None and off_m <= ON_ROUTE_M

    landmark = next((f for f in features if f["distance_m"] <= FEATURE_IS_THE_POINT_M), None)
    if landmark:
        head = landmark["name"]
    elif len(roads) >= 2:
        head = f"{_short(roads[0])} / {_short(roads[1])}"
    elif roads:
        head = _short(roads[0])
    elif features:
        head = f"Near {features[0]['name']}"
    else:
        head = None

    if town and head:
        name = f"{head}, {town[0]['name']}"
    elif town:
        name = f"{'In' if town[1] else 'Near'} {town[0]['name']}"
    elif head:
        name = head
    elif on_route:
        # Not the day's name: planners' titles are long enough to fill the screen.
        name = f"Route at {at_km} km"
    else:
        # Nothing worth saying; keep it generic so a later run can try again.
        name = poi.get("name") or "Waypoint"

    lines = []
    if on_route:
        where = f"{at_km} km into the day"
        if off_m is not None and off_m > 50:
            where += f", {round(off_m)} m off the route"
        lines.append(where + ".")
    elif off_m is not None:
        lines.append(f"{off_m / 1000:.1f} km from this day's route.")

    ele = poi.get("ele")
    if ele is None and idx >= 0 and off_m is not None and off_m <= 50:
        ele = points[idx].get("ele")
    if ele is not None:
        lines.append(f"Elevation {round(ele)} m.")

    if len(roads) > 1:
        shown = roads[:3]
        lines.append(f"Junction of {', '.join(shown[:-1])} and {shown[-1]}.")
    elif roads:
        lines.append(f"On {roads[0]}.")
    if town:
        lines.append(f"{'In' if town[1] else 'Near'} {town[0]['name']} ({town[0]['place']}).")
    if features:
        listed = ", ".join(f"{f['name']} ({f['kind']}, {f['distance_m']} m)" for f in features[:4])
        lines.append(f"Nearby: {listed}.")

    return {"name": name[:80], "notes": " ".join(lines) or None, "ele": ele}
