"""The one place outbound HTTP requests actually leave the process.

Every fetch goes through here so the URL scheme is checked once. It matters
because several base URLs are overridable by environment variable
(OPEN_METEO_BASE, FIXMYSTREET_BASE, the roadworks tile template), and urllib
will happily open `file://` or `ftp://` if one of those is pointed at it -
which is exactly what bandit's S310 warns about.
"""

import urllib.error
import urllib.parse
import urllib.request

ALLOWED_SCHEMES = frozenset({"http", "https"})


class UnsafeUrl(ValueError):
    """A URL we refuse to fetch, because of its scheme."""


def check_url(url: str) -> str:
    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise UnsafeUrl(
            f"Refusing to fetch a '{scheme or 'relative'}' URL; only http and https are allowed"
        )
    return url


def build_request(
    url: str,
    *,
    data: bytes | None = None,
    method: str | None = None,
    headers: dict[str, str] | None = None,
) -> urllib.request.Request:
    check_url(url)
    req = urllib.request.Request(url, data=data, method=method)  # noqa: S310 - scheme checked above
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    return req


def urlopen(req: urllib.request.Request, timeout: float):
    """Open a request built by `build_request`, re-checking the URL."""
    check_url(req.full_url)
    return urllib.request.urlopen(req, timeout=timeout)  # noqa: S310 - scheme checked above
