"""Strava OAuth and API access.

Personal, single-athlete use: one stored token set, refreshed on demand.
Credentials come from the environment so the client secret isn't in the database.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta

from . import http_client

API_BASE = "https://www.strava.com/api/v3"
OAUTH_AUTHORIZE = "https://www.strava.com/oauth/authorize"
OAUTH_TOKEN_URL = "https://www.strava.com/oauth/token"  # noqa: S105 - a URL, not a token

# read_all is needed to see routes you haven't made public.
SCOPES = "read,read_all,activity:read_all"


class StravaNotConfigured(RuntimeError):
    pass


class StravaError(RuntimeError):
    pass


def client_id() -> str:
    value = os.environ.get("STRAVA_CLIENT_ID", "").strip()
    if not value:
        raise StravaNotConfigured("STRAVA_CLIENT_ID is not set")
    return value


def client_secret() -> str:
    value = os.environ.get("STRAVA_CLIENT_SECRET", "").strip()
    if not value:
        raise StravaNotConfigured("STRAVA_CLIENT_SECRET is not set")
    return value


def redirect_uri() -> str:
    return os.environ.get("STRAVA_REDIRECT_URI", "http://localhost:8090/api/strava/callback")


def is_configured() -> bool:
    return bool(os.environ.get("STRAVA_CLIENT_ID") and os.environ.get("STRAVA_CLIENT_SECRET"))


def authorize_url(state: str = "") -> str:
    params = {
        "client_id": client_id(),
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": SCOPES,
    }
    if state:
        params["state"] = state
    return f"{OAUTH_AUTHORIZE}?{urllib.parse.urlencode(params)}"


def _post_form(url: str, data: dict) -> dict:
    body = urllib.parse.urlencode(data).encode()
    req = http_client.build_request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with http_client.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise StravaError(f"Strava returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise StravaError(f"Could not reach Strava: {exc}") from exc


def exchange_code(code: str) -> dict:
    return _post_form(
        OAUTH_TOKEN_URL,
        {
            "client_id": client_id(),
            "client_secret": client_secret(),
            "code": code,
            "grant_type": "authorization_code",
        },
    )


def refresh(refresh_token: str) -> dict:
    return _post_form(
        OAUTH_TOKEN_URL,
        {
            "client_id": client_id(),
            "client_secret": client_secret(),
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
    )


def _get(path: str, token: str, raw: bool = False):
    if path.startswith("http"):
        # Never send the bearer token to a host we did not choose ourselves.
        raise StravaError("Strava paths must be relative to the API base")
    req = http_client.build_request(
        f"{API_BASE}{path}", headers={"Authorization": f"Bearer {token}"}
    )
    try:
        with http_client.urlopen(req, timeout=60) as resp:
            payload = resp.read()
            return payload if raw else json.loads(payload.decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        if exc.code == 401:
            raise StravaError("Strava rejected the token (401). Reconnect the account.") from exc
        if exc.code == 429:
            raise StravaError("Strava rate limit reached. Try again shortly.") from exc
        raise StravaError(f"Strava returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise StravaError(f"Could not reach Strava: {exc}") from exc


def list_routes(token: str, page: int = 1, per_page: int = 50) -> list[dict]:
    return _get(f"/athlete/routes?page={page}&per_page={per_page}", token)


def export_route_gpx(token: str, route_id: int) -> bytes:
    return _get(f"/routes/{route_id}/export_gpx", token, raw=True)


def athlete(token: str) -> dict:
    return _get("/athlete", token)


def expiry_from(payload: dict) -> datetime:
    """Token expiry as a naive UTC datetime, matching how it's stored."""
    if "expires_at" in payload:
        return datetime.fromtimestamp(int(payload["expires_at"]), tz=UTC).replace(tzinfo=None)
    seconds = int(payload.get("expires_in", 21600))
    return datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=seconds)
