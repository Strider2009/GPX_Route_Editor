"""Pothole reports from FixMyStreet.

FixMyStreet's map endpoint takes a bounding box and returns pins. Two details
matter: `show_old_reports=1` is essential (without it you only get the last few
weeks, which for potholes is almost nothing), and each council names its own
categories, so the pothole categories are discovered from the national services
list rather than guessed.
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

from . import http_client

BASE = os.environ.get("FIXMYSTREET_BASE", "https://www.fixmystreet.com")
USER_AGENT = os.environ.get(
    "FIXMYSTREET_UA", "personal-gpx-route-planner/1.0 (personal cycling route checks)"
)
# A box returns at most this many pins, so a saturated box means we asked too big.
PIN_CAP = 100

# Used if the service list can't be reached. Deliberately short - the live list is
# the source of truth.
FALLBACK_CATEGORIES = [
    "Pothole",
    "Potholes",
    "Carriageway pothole",
    "Pothole in the road",
    "Road Potholes",
    "Potholes / Highway Condition",
]

_category_cache: dict[str, object] = {"names": None, "at": 0.0}
_CATEGORY_TTL = 24 * 3600

# FixMyStreet report ids are sequential, and the pin payload carries no date, so the
# id is the only cheap age signal available. These are sampled real reports; the
# result is an estimate good to a few months, which is enough to tell a live report
# from one filed years ago and never closed.
_ID_DATE_CALIBRATION = [
    (746_585, date(2016, 1, 15)),
    (834_800, date(2016, 6, 3)),
    (1_899_502, date(2019, 12, 20)),
    (4_158_915, date(2023, 1, 22)),
    (9_631_464, date(2026, 6, 16)),
]


def estimate_report_date(report_id) -> date | None:
    """Approximate when a report was filed, interpolated from its id."""
    try:
        rid = int(report_id)
    except (TypeError, ValueError):
        return None

    points = _ID_DATE_CALIBRATION
    if rid <= points[0][0]:
        return points[0][1]
    if rid >= points[-1][0]:
        # Extrapolate using the most recent segment's rate.
        (id_a, date_a), (id_b, date_b) = points[-2], points[-1]
        per_id = (date_b - date_a).days / max(1, id_b - id_a)
        return date_b + timedelta(days=int((rid - id_b) * per_id))

    for (id_a, date_a), (id_b, date_b) in zip(points, points[1:], strict=False):
        if id_a <= rid <= id_b:
            frac = (rid - id_a) / max(1, id_b - id_a)
            return date_a + timedelta(days=int((date_b - date_a).days * frac))
    return None


def _get(url: str, timeout: float = 60.0) -> bytes:
    req = http_client.build_request(url, headers={"User-Agent": USER_AGENT})
    with http_client.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def pothole_categories(force: bool = False) -> list[str]:
    """Every council category whose name mentions a pothole."""
    now = time.time()
    cached = _category_cache.get("names")
    if cached and not force and now - float(_category_cache["at"]) < _CATEGORY_TTL:
        return cached  # type: ignore[return-value]

    try:
        raw = _get(f"{BASE}/open311/v2/services.json?jurisdiction_id=fixmystreet.com")
        services = json.loads(raw.decode("utf-8", "replace"))
        if isinstance(services, dict):
            services = services.get("services", [])
        names = sorted(
            {
                s["service_name"]
                for s in services
                if isinstance(s, dict) and "pothole" in str(s.get("service_name", "")).lower()
            }
        )
        if names:
            _category_cache["names"] = names
            _category_cache["at"] = now
            return names
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, KeyError, TimeoutError):
        pass
    return list(FALLBACK_CATEGORIES)


def fetch_bbox(
    west: float, south: float, east: float, north: float, categories: list[str]
) -> list[dict]:
    """Pins for one bounding box. Returns [{lat, lon, colour, report_id, title}]."""
    params = [
        ("bbox", f"{west:.6f},{south:.6f},{east:.6f},{north:.6f}"),
        # Without this you only see the most recent handful - useless for potholes,
        # which sit unrepaired for months.
        ("show_old_reports", "1"),
        ("status", "open"),
    ]
    params += [("filter_category", c) for c in categories]
    url = f"{BASE}/ajax?{urllib.parse.urlencode(params)}"

    payload = json.loads(_get(url).decode("utf-8", "replace"))
    out = []
    for pin in payload.get("pins", []):
        # [lat, lon, colour, id, title, extra, flag]
        if len(pin) < 5:
            continue
        out.append(
            {
                "lat": float(pin[0]),
                "lon": float(pin[1]),
                "colour": pin[2],
                "report_id": str(pin[3]),
                "title": pin[4],
            }
        )
    return out


def fetch_boxes(boxes: list[tuple[float, float, float, float]], delay_s: float = 0.3):
    """Yield (box, pins, saturated, error) for each box, pacing between requests."""
    categories = pothole_categories()
    for i, box in enumerate(boxes):
        if i:
            time.sleep(delay_s)
        try:
            pins = fetch_bbox(*box, categories)
            yield box, pins, len(pins) >= PIN_CAP, None
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError) as exc:
            yield box, [], False, str(exc)
