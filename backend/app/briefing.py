"""Assembling a rider's briefing for a day.

Two layers, deliberately separate. `gather` computes the facts and is the useful
half: it needs no API key, costs nothing, and always works. `narrate` turns
those facts into prose with Claude and is optional.

Nothing here touches Strava. Its API policy forbids putting Strava data - or
anything derived from it - into a model's context, so the briefing is built from
the route's own geometry plus OpenStreetMap, which carries no such restriction.
"""

import hashlib
import os
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from . import climbs as climbs_mod
from . import overpass_fetch
from .geo import cumulative_distance, distance_to_route, elevation_gain_loss
from .models import NarrativeCache, PlaceLookup

# Empty-string safe: compose passes unset optional vars through as "".
MODEL = os.environ.get("BRIEFING_MODEL") or "claude-opus-5"


def _route_key(points: list[dict], buffer_m: int) -> str:
    """A fingerprint of the route's shape, so an edit invalidates the cache."""
    thinned = overpass_fetch._thin(points)
    blob = ";".join(f"{p['lat']:.4f},{p['lon']:.4f}" for p in thinned)
    digest = hashlib.sha1(blob.encode(), usedforsecurity=False).hexdigest()[:16]
    return f"places:{buffer_m}:{digest}"


def _places_cached(
    db: Session | None, points: list[dict], buffer_m: int, refresh: bool
) -> list[dict]:
    """Settlements near the route, asking Overpass at most once per route shape."""
    if db is None:
        return overpass_fetch.places_along_route(points, buffer_m=buffer_m)

    key = _route_key(points, buffer_m)
    row = db.query(PlaceLookup).filter(PlaceLookup.key == key).one_or_none()
    if row is not None and not refresh:
        return list(row.payload or [])

    found = overpass_fetch.places_along_route(points, buffer_m=buffer_m)
    if row is None:
        row = PlaceLookup(key=key)
        db.add(row)
    row.payload = found
    row.fetched_at = datetime.now(UTC)
    db.commit()
    return found


def _ordered_places(points: list[dict], places: list[dict], buffer_m: int) -> list[dict]:
    """Settlements the route actually passes, in the order it reaches them.

    The lookup asks for a bounding box because that is the only shape Overpass
    answers quickly, so the corridor filter happens here: a place in the corner
    of the box can be miles from the road.

    Two places can sit near the same stretch; the nearer one wins that position,
    and a place the route returns to is named once, at its first appearance.
    """
    # Two passes, because the precise test is O(places x points) and a long day
    # is thousands of points. The coarse route is every ~500 m, so a place can
    # sit at most ~half that further from it than from the real line; anything
    # beyond buffer + that margin cannot possibly qualify and is dropped without
    # the expensive check.
    coarse = overpass_fetch._thin(points)
    margin = buffer_m + 400.0

    placed = []
    for p in places:
        rough, _ = distance_to_route(p["lat"], p["lon"], coarse)
        if rough > margin:
            continue
        gap, idx = distance_to_route(p["lat"], p["lon"], points)
        if gap > buffer_m:
            continue
        placed.append({**p, "distance_m": round(gap, 1), "at_index": idx})

    placed.sort(key=lambda p: (p["at_index"], p["distance_m"]))

    seen: set[str] = set()
    out = []
    for p in placed:
        if p["name"] in seen:
            continue
        seen.add(p["name"])
        p["at_km"] = round(_distance_along(points, p["at_index"]) / 1000.0, 1)
        out.append(p)
    return out


def _spaced_out(places: list[dict], spacing_km: float) -> list[dict]:
    """At most one place per spacing_km of route, keeping the one worth naming.

    A briefing is a sense of progress, not a gazetteer: the useful line is "Rye
    at 56 km", not the four hamlets either side of it. Within each window the
    largest settlement wins, and ties go to whichever is closest to the road -
    so a town is never dropped in favour of a hamlet that happened to come
    first.
    """
    if spacing_km <= 0 or not places:
        return places

    buckets: dict[int, dict] = {}
    for p in places:
        slot = int(p["at_km"] // spacing_km)
        best = buckets.get(slot)
        if best is None or (p["rank"], p["distance_m"]) < (best["rank"], best["distance_m"]):
            buckets[slot] = p

    chosen = sorted(buckets.values(), key=lambda p: p["at_km"])

    # Neighbouring buckets can still put two places close together when one sits
    # just after a boundary, so enforce the spacing itself as well.
    out: list[dict] = []
    for p in chosen:
        if out and p["at_km"] - out[-1]["at_km"] < spacing_km:
            if (p["rank"], p["distance_m"]) < (out[-1]["rank"], out[-1]["distance_m"]):
                out[-1] = p
            continue
        out.append(p)
    return out


def _distance_along(points: list[dict], index: int) -> float:
    return cumulative_distance(points[: index + 1]) if index else 0.0


def gather(
    day,
    include_places: bool = True,
    buffer_m: int = 100,
    spacing_km: float = 10.0,
    db: Session | None = None,
    refresh: bool = False,
) -> dict:
    """Everything worth saying about a day, as structured facts."""
    points = day.points or []
    ascent, descent = elevation_gain_loss(points)
    total_m = cumulative_distance(points)

    found = climbs_mod.find_climbs(points)
    for c in found:
        c["at_km"] = round(_distance_along(points, c["start_index"]) / 1000.0, 1)

    places: list[dict] = []
    places_error = None
    if include_places and points:
        try:
            raw = _places_cached(db, points, buffer_m, refresh)
            places = _spaced_out(_ordered_places(points, raw, buffer_m), spacing_km)
        except overpass_fetch.OverpassError as exc:
            # A briefing without place names is still worth having.
            places_error = str(exc)

    return {
        "day_id": day.id,
        "name": day.name,
        "is_circular": day.is_circular,
        "distance_km": round(total_m / 1000.0, 1),
        "ascent_m": round(ascent),
        "descent_m": round(descent),
        "point_count": len(points),
        "profile": climbs_mod.profile_summary(points),
        "climbs": found,
        "places": places,
        "places_error": places_error,
        "pois": [
            {"name": p.name, "symbol": p.symbol, "notes": p.notes, "lat": p.lat, "lon": p.lon}
            for p in day.pois
        ],
        "connectors": [{"name": c.name, "type": c.type} for c in day.connectors],
    }


def _facts_prompt(facts: dict) -> str:
    lines = [
        f"Day: {facts['name']}",
        f"Distance: {facts['distance_km']} km",
        f"Climbing: {facts['ascent_m']} m up, {facts['descent_m']} m down",
        f"Loop: {'yes' if facts['is_circular'] else 'no, point to point'}",
    ]
    profile = facts.get("profile") or {}
    if profile.get("has_elevation"):
        lines.append(f"Altitude range: {profile['min_ele_m']}-{profile['max_ele_m']} m")

    if facts["places"]:
        lines.append("")
        lines.append("Places passed, in order (km from the start):")
        for p in facts["places"]:
            lines.append(
                f"  {p['at_km']} km - {p['name']} ({p['place']}, {p['distance_m']} m off route)"
            )

    if facts["climbs"]:
        lines.append("")
        lines.append("Climbs, in order:")
        for c in facts["climbs"]:
            cat = f"cat {c['category']}" if c["category"] else "uncategorised"
            lines.append(
                f"  {c['at_km']} km - {c['length_m']:.0f} m at {c['avg_gradient']}% average, "
                f"{c['gain_m']:.0f} m gain, steepest {c['max_gradient']}%, {cat}"
            )
    else:
        lines.append("")
        lines.append("No sustained climbs were detected.")

    if facts["pois"]:
        lines.append("")
        lines.append("Marked stops:")
        for p in facts["pois"]:
            note = f" - {p['notes']}" if p["notes"] else ""
            lines.append(f"  {p['name']} ({p['symbol'] or 'POI'}){note}")

    return "\n".join(lines)


SYSTEM = """You write short pre-ride briefings for a cyclist planning a multi-day trip.

You are given measured facts about one day's route. Write a briefing of three to \
five short paragraphs covering, in this order: the shape of the day overall; the \
climbs and where they fall; the places the route passes and roughly when; and any \
marked stops.

Rules:
- Use only the facts given. Do not invent road names, surfaces, traffic, scenery, \
weather or anything else you were not told.
- Refer to places by the names given, in the order given.
- Be concrete about distances and gradients. A rider is deciding what to carry and \
when to eat.
- Plain British English, no bullet lists, no headings, no preamble. Start with the \
first sentence of the briefing itself.
- If the facts are thin, write less rather than padding."""


class BriefingUnavailable(RuntimeError):
    """No API key configured, or the model could not be reached."""


def narrate(
    facts: dict,
    effort: str = "medium",
    db: Session | None = None,
    refresh: bool = False,
) -> str:
    """Turn the gathered facts into prose. Requires ANTHROPIC_API_KEY.

    Cached against the exact prompt, so re-opening a briefing is free and only a
    real change to the day costs another call.
    """
    prompt = _facts_prompt(facts)
    key = hashlib.sha1(f"{MODEL}\n{prompt}".encode(), usedforsecurity=False).hexdigest()

    if db is not None and not refresh:
        hit = db.query(NarrativeCache).filter(NarrativeCache.key == key).one_or_none()
        if hit is not None:
            return hit.text

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise BriefingUnavailable(
            "ANTHROPIC_API_KEY is not set, so the written briefing is unavailable. "
            "The route facts above are unaffected."
        )
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        raise BriefingUnavailable("The anthropic package is not installed.") from exc

    client = anthropic.Anthropic()
    try:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=8000,
            system=SYSTEM,
            thinking={"type": "adaptive"},
            output_config={"effort": effort},
            # Routed automatically if a safety classifier declines, so a briefing
            # never fails outright for a reason the rider can do nothing about.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller as 502
        raise BriefingUnavailable(f"Could not reach the model: {exc}") from exc

    if response.stop_reason == "refusal":
        raise BriefingUnavailable("The model declined to write this briefing.")

    text = "\n\n".join(b.text.strip() for b in response.content if b.type == "text").strip()

    if db is not None and text:
        row = db.query(NarrativeCache).filter(NarrativeCache.key == key).one_or_none()
        if row is None:
            row = NarrativeCache(key=key)
            db.add(row)
        row.model = MODEL
        row.text = text
        row.created_at = datetime.now(UTC)
        db.commit()

    return text
