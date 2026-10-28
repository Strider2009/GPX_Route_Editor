"""Where terrain heights come from.

Each source of elevation is a provider behind the same small interface, so the
app never knows which one it is talking to: filling a route, or comparing
sources against a route's recorded heights, just asks the registry by id.
Adding a source means writing one `_fetch_batch` and registering it below.

All of these are digital elevation models - the height of the ground on a
grid - so they read a little differently to a GPS or barometric track: smoother,
and blind to bridges and cuttings, where the model shows the valley floor or
the hill the road cuts through.
"""

import json
import os
import threading
import time
import urllib.error
import urllib.parse
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Callable

from .. import http_client

USER_AGENT = "personal-gpx-route-planner/1.0 (personal cycling route planning)"

# Coordinates are rounded before lookup so repeats (a loop's closing point, the
# point two days share) cost nothing. 6 dp is about 0.1 m - far below any grid.
COORD_DP = 6

Coord = tuple[float, float]
# Called after each batch with (points looked up so far, points to look up).
Progress = Callable[[int, int], None]

# How many times one batch is retried after the provider says to slow down.
RATE_LIMIT_RETRIES = 3


class ElevationError(RuntimeError):
    """A provider couldn't answer. The message is safe to show the user."""


class RateLimited(ElevationError):
    """The provider wants us to back off before asking again."""


class ElevationProvider(ABC):
    id: str
    label: str
    description: str
    # Most of these APIs cap a request at 100 locations.
    batch_size: int = 100
    # Seconds to leave between requests, for hosts that limit calls.
    min_interval_s: float = 0.0
    # For hosts that count every location as a call. None means no limit to pace for.
    points_per_minute: int | None = None
    # How long to back off when the host says it's had enough.
    retry_after_s: float = 60.0

    def lookup(self, coords: list[Coord], progress: Progress | None = None) -> list[float | None]:
        """Heights for each coordinate, in order. None where the model has no data.

        Paced to stay inside the host's limits, so a long route can take minutes
        on a rate-limited provider - run big lookups off the request thread.
        """
        keys = [(round(lat, COORD_DP), round(lon, COORD_DP)) for lat, lon in coords]
        unique = list(dict.fromkeys(keys))
        found: dict[Coord, float | None] = {}
        limiter = _limiter(self._host())
        for start in range(0, len(unique), self.batch_size):
            batch = unique[start : start + self.batch_size]
            heights = self._fetch_paced(limiter, batch)
            if len(heights) != len(batch):
                raise ElevationError(
                    f"{self.label} returned {len(heights)} heights for {len(batch)} points"
                )
            found.update(zip(batch, heights, strict=True))
            if progress:
                progress(len(found), len(unique))
        return [found[k] for k in keys]

    def _fetch_paced(self, limiter: "_HostLimiter", batch: list[Coord]) -> list[float | None]:
        for attempt in range(RATE_LIMIT_RETRIES + 1):
            limiter.wait(len(batch), self.min_interval_s, self.points_per_minute)
            try:
                return self._fetch_batch(batch)
            except RateLimited:
                if attempt == RATE_LIMIT_RETRIES:
                    raise
                # Our own pacing can't see calls made before a restart, or by
                # anything else sharing this IP, so the host gets the last word.
                time.sleep(self.retry_after_s)
        raise AssertionError("unreachable")

    @abstractmethod
    def _fetch_batch(self, coords: list[Coord]) -> list[float | None]: ...

    @abstractmethod
    def _host(self) -> str: ...

    def info(self) -> dict:
        return {"id": self.id, "label": self.label, "description": self.description}


class _HostLimiter:
    """Pacing for one host, shared by every provider on it and every thread.

    The lock is held while waiting, which queues callers in order - exactly what
    a host with a per-minute budget wants.
    """

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.last_call = 0.0
        self.recent: deque[tuple[float, int]] = deque()  # (when, points) in the last minute

    def wait(self, points: int, min_interval: float, per_minute: int | None) -> None:
        with self.lock:
            now = time.monotonic()
            if min_interval > 0 and now < self.last_call + min_interval:
                time.sleep(self.last_call + min_interval - now)
            if per_minute:
                while True:
                    now = time.monotonic()
                    while self.recent and self.recent[0][0] <= now - 60:
                        self.recent.popleft()
                    used = sum(n for _, n in self.recent)
                    if not self.recent or used + points <= per_minute:
                        break
                    time.sleep(self.recent[0][0] + 60 - now + 0.05)
                self.recent.append((time.monotonic(), points))
            self.last_call = time.monotonic()


_limiters: dict[str, _HostLimiter] = {}
_limiters_lock = threading.Lock()


def _limiter(host: str) -> _HostLimiter:
    with _limiters_lock:
        return _limiters.setdefault(host, _HostLimiter())


def _get_json(url: str, label: str) -> dict:
    req = http_client.build_request(url, headers={"User-Agent": USER_AGENT})
    try:
        with http_client.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise RateLimited(f"{label} is rate-limiting us - try again in a minute") from e
        raise ElevationError(f"{label} refused the request ({e.code})") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise ElevationError(f"Couldn't reach {label}") from e
    except json.JSONDecodeError as e:
        raise ElevationError(f"{label} sent back something that wasn't JSON") from e


class OpenMeteo(ElevationProvider):
    id = "open-meteo"
    label = "Open-Meteo"
    description = "Copernicus GLO-90 (~90 m). Free, no key; about 600 points a minute."
    # The free tier counts each location as a call: 600 a minute. Leave headroom
    # for weather lookups, which share the host.
    points_per_minute = 500

    def __init__(self, base: str | None = None):
        self.base = (
            base
            or os.environ.get("OPEN_METEO_ELEVATION_BASE")
            or "https://api.open-meteo.com/v1/elevation"
        )

    def _host(self) -> str:
        return urllib.parse.urlparse(self.base).netloc

    def _fetch_batch(self, coords: list[Coord]) -> list[float | None]:
        query = urllib.parse.urlencode(
            {
                "latitude": ",".join(f"{lat:.{COORD_DP}f}" for lat, _ in coords),
                "longitude": ",".join(f"{lon:.{COORD_DP}f}" for _, lon in coords),
            }
        )
        body = _get_json(f"{self.base}?{query}", self.label)
        if body.get("error"):
            raise ElevationError(f"{self.label}: {body.get('reason') or 'request rejected'}")
        heights = body.get("elevation")
        if not isinstance(heights, list):
            raise ElevationError(f"{self.label} sent back no elevations")
        # Open-Meteo reports sea and missing tiles as NaN, which json reads as float('nan').
        return [None if h is None or h != h else float(h) for h in heights]


class OpenTopoData(ElevationProvider):
    """One dataset on an OpenTopoData server. The public one allows ~1 call/s, 1000/day."""

    min_interval_s = 1.05
    retry_after_s = 5.0

    def __init__(self, dataset: str, label: str, description: str, base: str | None = None):
        self.dataset = dataset
        self.id = f"opentopodata-{dataset}"
        self.label = label
        self.description = description
        self.base = base or os.environ.get("OPENTOPODATA_BASE") or "https://api.opentopodata.org/v1"

    def _host(self) -> str:
        return urllib.parse.urlparse(self.base).netloc

    def _fetch_batch(self, coords: list[Coord]) -> list[float | None]:
        locations = "|".join(f"{lat:.{COORD_DP}f},{lon:.{COORD_DP}f}" for lat, lon in coords)
        url = f"{self.base}/{self.dataset}?{urllib.parse.urlencode({'locations': locations})}"
        body = _get_json(url, self.label)
        if body.get("status") != "OK":
            raise ElevationError(
                f"{self.label}: {body.get('error') or body.get('status') or 'request rejected'}"
            )
        return [
            float(r["elevation"]) if r.get("elevation") is not None else None
            for r in body.get("results", [])
        ]


PROVIDERS: dict[str, ElevationProvider] = {
    p.id: p
    for p in (
        OpenMeteo(),
        OpenTopoData(
            "eudem25m", "EU-DEM 25 m", "European 25 m model via OpenTopoData. Rate-limited."
        ),
        OpenTopoData("srtm30m", "SRTM 30 m", "NASA SRTM 30 m via OpenTopoData. Rate-limited."),
    )
}


def default_provider_id() -> str:
    chosen = os.environ.get("ELEVATION_PROVIDER") or OpenMeteo.id
    return chosen if chosen in PROVIDERS else OpenMeteo.id


def get_provider(provider_id: str | None = None) -> ElevationProvider:
    pid = provider_id or default_provider_id()
    try:
        return PROVIDERS[pid]
    except KeyError:
        raise ElevationError(f"Unknown elevation provider '{pid}'") from None
