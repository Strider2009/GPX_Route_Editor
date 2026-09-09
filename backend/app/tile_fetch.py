"""Fetch roadworks vector tiles directly, for the tiles a route actually covers.

Deliberately modest: only the tiles covering the requested route, fetched
sequentially with a delay, on an explicit user action - never in the background.
The URL template is configurable because it is not a documented API and may change.
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import http_client

DEFAULT_TEMPLATE = os.environ.get(
    "ROADWORKS_TILE_TEMPLATE",
    "https://eu2-prd-pg-ts1.one.network/tileserv.maplayer_roadworks/{z}/{x}/{y}.pbf",
)
DEFAULT_REFERER = os.environ.get("ROADWORKS_TILE_REFERER", "https://one.network/")
USER_AGENT = os.environ.get(
    "ROADWORKS_TILE_UA",
    "Mozilla/5.0 (compatible; personal-gpx-route-planner/1.0)",
)
LONDON = ZoneInfo("Europe/London")

# Mirrors the map's default filter set: everything except cancelled/revoked.
DEFAULT_FILTERS = {
    "impact": ["-1", "0", "1", "2", "3", "4"],
    "works_state": ["-1", "0", "2", "3", "4", "5", "6", "8"],
    "permit_status": ["-1", "0", "101", "11", "12", "13", "25", "26", "27", "28", "29", "30", "4"],
    "ttro_state": ["-100", "4", "5"],
}


def _date_bounds(day: datetime) -> tuple[str, str]:
    """Local-day bounds expressed the way the tile server expects them."""
    start_local = day.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=LONDON)
    end_local = start_local + timedelta(days=1) - timedelta(seconds=1)
    fmt = "%d/%m/%Y %H:%M:%S"
    return (
        start_local.astimezone(ZoneInfo("UTC")).strftime(fmt),
        end_local.astimezone(ZoneInfo("UTC")).strftime(fmt),
    )


def build_tile_url(
    z: int, x: int, y: int, target_date: datetime, template: str = DEFAULT_TEMPLATE
) -> str:
    start, end = _date_bounds(target_date)
    params = {
        "predefineddates": "true",
        "startdate": start,
        "enddate": end,
        "tz": "Europe/London",
        "publicuser": "1",
        "organisationid": "1",
        "extendedfunctionid": "14",
        "ownworksflag": "0",
        "tmshowunpublished": "0",
        "tags": "notags",
        "lang": "en-US",
        "filters": json.dumps(DEFAULT_FILTERS, separators=(",", ":")),
    }
    base = template.format(z=z, x=x, y=y)
    return f"{base}?{urllib.parse.urlencode(params)}"


def fetch_tile(url: str, timeout: float = 20.0) -> bytes:
    req = http_client.build_request(
        url,
        headers={"User-Agent": USER_AGENT, "Referer": DEFAULT_REFERER, "Accept": "*/*"},
    )
    with http_client.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}")
        return resp.read()


def fetch_tiles(
    tiles: list[tuple[int, int, int]],
    target_date: datetime,
    delay_s: float = 0.25,
    template: str = DEFAULT_TEMPLATE,
):
    """Yield (z, x, y, data, error) for each tile, pacing between requests."""
    for i, (z, x, y) in enumerate(tiles):
        if i:
            time.sleep(delay_s)
        url = build_tile_url(z, x, y, target_date, template)
        try:
            yield z, x, y, fetch_tile(url), None
        except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError, TimeoutError) as exc:
            yield z, x, y, None, str(exc)
