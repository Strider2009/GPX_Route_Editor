"""Places near a point, from OpenStreetMap via Overpass.

Overpass is run on donated hardware, so every result is cached (see VenueArea)
and a repeat search costs nothing. The public instances rate-limit hard; set
OVERPASS_BASE to your own if you ever need volume.

OSM has no ratings and never will - it records verifiable ground truth, and
"is the coffee good" is not verifiable. What it does have is the things that
actually decide a stop on a long ride: whether it is open when you get there,
whether you can leave a bike outside, whether there is water.
"""

import json
import math
import os
import time
import urllib.error
import urllib.parse

from . import http_client

# `or` rather than a get() default: docker-compose passes unset optional vars
# through as empty strings, which would otherwise blank these out entirely.
BASE = os.environ.get("OVERPASS_BASE") or "https://overpass-api.de/api/interpreter"
USER_AGENT = (
    os.environ.get("OVERPASS_UA")
    or "personal-gpx-route-planner/1.0 (personal cycling route planning)"
)

# What each kind means in OSM tags. Kept explicit rather than clever: these are
# the stops that matter on a ride, and the tag vocabulary is stable.
KINDS: dict[str, list[str]] = {
    "cafe": ['["amenity"="cafe"]', '["shop"="coffee"]', '["shop"="bakery"]'],
    "food": ['["amenity"="restaurant"]', '["amenity"="fast_food"]', '["amenity"="pub"]'],
    "water": ['["amenity"="drinking_water"]', '["man_made"="water_tap"]'],
    "toilets": ['["amenity"="toilets"]'],
    "bicycle": ['["shop"="bicycle"]', '["amenity"="bicycle_repair_station"]'],
}

# Tags worth keeping. Chosen from what UK data actually carries rather than from
# the wiki: surveying Bristol, 83% of cafes have an address, 29% a check_date,
# and the water features lean on `fountain` to say what they actually are.
KEEP_TAGS = (
    # What is it, and can I use it
    "fountain",  # bottle_refill | bubbler | drinking - the difference that matters
    "bottle",  # explicitly whether a bottle fits under it
    "drinking_water",
    "fee",
    "access",
    "indoor",
    "covered",
    "seasonal",
    "opening_hours",
    "description",
    # Who and where
    "operator",
    "brand",
    "website",
    "phone",
    "email",
    # Worth knowing on a bike
    "bicycle_parking",
    "outdoor_seating",
    "indoor_seating",
    "takeaway",
    "cuisine",
    "internet_access",
    "wheelchair",
    "diet:vegetarian",
    "diet:vegan",
    "dog",
    # How much to trust it: OSM records when a mapper last verified the feature.
    "check_date",
    "survey:date",
    "check_date:opening_hours",
    # The UK Food Hygiene Rating Scheme id, where a mapper has linked one.
    "fhrs:id",
)

# Address is spread across several keys; it reads better as one line.
ADDR_KEYS = ("addr:housename", "addr:housenumber", "addr:street", "addr:suburb", "addr:postcode")


def _address(tags: dict) -> str | None:
    house = tags.get("addr:housenumber") or tags.get("addr:housename")
    street = tags.get("addr:street")
    first = " ".join(x for x in (house, street) if x)
    parts = [p for p in (first, tags.get("addr:suburb"), tags.get("addr:postcode")) if p]
    return ", ".join(parts) or None


def _is_usable(tags: dict, kind: str) -> bool:
    """Drop things that would be actively misleading to show.

    A `man_made=water_tap` tagged `drinking_water=no` is a real thing in OSM and
    listing it under "water" would send you to fill a bottle from a tap someone
    has explicitly recorded as not drinkable.
    """
    if any(k.startswith(("disused:", "abandoned:", "removed:")) for k in tags):
        return False
    if tags.get("operational_status") in ("closed", "broken"):
        return False
    if kind == "water":
        if tags.get("drinking_water") == "no" or tags.get("drinking_water:legal") == "no":
            return False
        if tags.get("access") in ("private", "no"):
            return False
    return True


# Unnamed things are usually fine for water and toilets but useless for a cafe.
NAMELESS_OK = {"water", "toilets"}


class OverpassError(RuntimeError):
    """Overpass could not be reached, or refused the query."""


def build_query(lat: float, lon: float, radius_m: int, kinds: list[str]) -> str:
    clauses = []
    for kind in kinds:
        for selector in KINDS.get(kind, []):
            # nwr covers nodes, ways and relations; a cafe inside a building is a way.
            clauses.append(f"  nwr{selector}(around:{radius_m},{lat:.6f},{lon:.6f});")
    body = "\n".join(clauses)
    # `out center` gives ways and relations a single representative point.
    return f"[out:json][timeout:25];\n(\n{body}\n);\nout center tags;"


def _kind_of(tags: dict) -> str | None:
    """Which kind a result belongs to, by the tag that matched."""
    amenity, shop = tags.get("amenity"), tags.get("shop")
    if amenity == "cafe" or shop in ("coffee", "bakery"):
        return "cafe"
    if amenity in ("restaurant", "fast_food", "pub"):
        return "food"
    if amenity == "drinking_water" or tags.get("man_made") == "water_tap":
        return "water"
    if amenity == "toilets":
        return "toilets"
    if shop == "bicycle" or amenity == "bicycle_repair_station":
        return "bicycle"
    return None


def search(lat: float, lon: float, radius_m: int, kinds: list[str]) -> list[dict]:
    """Places of the given kinds within radius_m of a point.

    Returns [{external_id, name, kind, lat, lon, tags}]. Raises OverpassError
    rather than returning nothing, so a rate-limit reads as a failure the user
    can retry rather than as "there are no cafes here".
    """
    query = build_query(lat, lon, radius_m, kinds)
    if "nwr" not in query:
        return []

    payload = _post(query)

    out = []
    seen = set()
    for el in payload.get("elements", []):
        tags = el.get("tags") or {}
        kind = _kind_of(tags)
        if kind is None or kind not in kinds:
            continue
        if not _is_usable(tags, kind):
            continue

        point = el if el.get("lat") is not None else el.get("center") or {}
        lat_v, lon_v = point.get("lat"), point.get("lon")
        if lat_v is None or lon_v is None:
            continue

        name = tags.get("name")
        if not name:
            if kind not in NAMELESS_OK:
                continue
            name = {"water": "Drinking water", "toilets": "Toilets"}.get(kind, "Unnamed")

        external_id = f"{el.get('type', 'node')}/{el.get('id')}"
        if external_id in seen:
            continue
        seen.add(external_id)

        out.append(
            {
                "external_id": external_id,
                "name": name,
                "kind": kind,
                "lat": float(lat_v),
                "lon": float(lon_v),
                "tags": _kept_tags(tags),
            }
        )
    return out


def _kept_tags(tags: dict) -> dict:
    kept = {k: tags[k] for k in KEEP_TAGS if k in tags}
    address = _address(tags)
    if address:
        kept["address"] = address
    # A tap with no `fountain` tag and no `bottle` tag is the ambiguous case the
    # UI has to be honest about, so record that we looked rather than guessing.
    if tags.get("man_made") == "water_tap" and "fountain" not in kept:
        kept.setdefault("fountain", "tap")
    return kept


# Settlements, largest first. A briefing wants "through Chew Magna", not a list
# of every hamlet within a mile.
#
# `suburb` is deliberately absent: a city contributes one useful name, but its
# suburbs contribute a dozen at the same point on the route. Canterbury alone
# returned six, all at 0.0 km, which buries the places that actually mark
# progress. The city itself is still named.
PLACE_RANKS = ["city", "town", "village", "hamlet"]


def _thin(points: list[dict], every_m: float = 500.0) -> list[dict]:
    """Every ~500 m of the route.

    Overpass takes a polyline for `around`, which is far tighter than a bounding
    box on a route that bends - but the query is sent as text, so a 5,000-point
    day has to be thinned before it goes in.
    """
    from .geo import haversine

    if not points:
        return []
    kept = [points[0]]
    run = 0.0
    for a, b in zip(points, points[1:], strict=False):
        run += haversine(a, b)
        if run >= every_m:
            kept.append(b)
            run = 0.0
    if kept[-1] is not points[-1]:
        kept.append(points[-1])
    return kept


def _bbox(points: list[dict], pad_m: float) -> tuple[float, float, float, float]:
    """South, west, north, east around the route, padded by roughly pad_m."""
    lats = [p["lat"] for p in points]
    lons = [p["lon"] for p in points]
    mid = (min(lats) + max(lats)) / 2
    dlat = pad_m / 111_320.0
    dlon = pad_m / max(1.0, 111_320.0 * math.cos(math.radians(mid)))
    return (min(lats) - dlat, min(lons) - dlon, max(lats) + dlat, max(lons) + dlon)


def _post(query: str, attempts: int = 3) -> dict:
    """Send a query, retrying the transient failures.

    429 and 504 both mean "not now" rather than "no": the public instances shed
    load aggressively, and a short wait usually clears it.
    """
    data = urllib.parse.urlencode({"data": query}).encode()
    last: Exception | None = None

    for attempt in range(attempts):
        if attempt:
            time.sleep(2.0 * attempt)
        req = http_client.build_request(
            BASE,
            data=data,
            method="POST",
            headers={
                "User-Agent": USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        try:
            with http_client.urlopen(req, timeout=90.0) as resp:
                return json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 504):
                raise OverpassError(f"Overpass returned HTTP {exc.code}") from exc
            last = exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            last = exc

    raise OverpassError(
        f"Overpass is busy and did not answer after {attempts} attempts. "
        f"Try again shortly, or set OVERPASS_BASE to your own instance. ({last})"
    )


def places_along_route(points: list[dict], buffer_m: int = 1200) -> list[dict]:
    """Named settlements near the route, unordered and unfiltered.

    Asked for as a bounding box rather than as a corridor around the polyline.
    `around:` with a long coordinate list cannot use the spatial index and takes
    seconds where a box takes milliseconds - on a full day's route that is the
    difference between an answer and a gateway timeout. The box is wider than
    the route, so the caller filters by real distance to the line.
    """
    thinned = _thin(points)
    if not thinned:
        return []
    south, west, north, east = _bbox(thinned, buffer_m)
    kinds = "|".join(PLACE_RANKS)
    query = f"""[out:json][timeout:40];
node["place"~"^({kinds})$"]["name"]({south:.5f},{west:.5f},{north:.5f},{east:.5f});
out tags center;"""

    payload = _post(query)

    out = []
    for el in payload.get("elements", []):
        tags = el.get("tags") or {}
        name = tags.get("name")
        place = tags.get("place")
        if not name or place not in PLACE_RANKS:
            continue
        lat, lon = el.get("lat"), el.get("lon")
        if lat is None or lon is None:
            continue
        out.append(
            {
                "name": name,
                "place": place,
                "rank": PLACE_RANKS.index(place),
                "lat": float(lat),
                "lon": float(lon),
                "population": tags.get("population"),
            }
        )
    return out
