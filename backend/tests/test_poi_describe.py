"""Describing waypoints from what is around them.

The Overpass call is not tested; the parts worth pinning down are which names
count as unset, and how the found roads, landmarks and towns become a name.
"""

from conftest import line

from app.geo import haversine
from app.poi_describe import build_query, describe, is_generic, nearby, settlement

AT = {"lat": 51.0045, "lon": 1.0, "name": "Waypoint", "ele": None}


def road(name, ref=None, lon=1.0):
    """A north-south way passing the test point."""
    tags = {"highway": "secondary", "name": name}
    if ref:
        tags["ref"] = ref
    return {
        "type": "way",
        "id": hash((name, lon)),
        "tags": tags,
        "geometry": [{"lat": 51.003, "lon": lon}, {"lat": 51.006, "lon": lon}],
    }


def node(name, lat=51.0045, lon=1.0, **tags):
    return {
        "type": "node",
        "id": hash(name),
        "lat": lat,
        "lon": lon,
        "tags": {"name": name, **tags},
    }


TOWN = {"name": "Rye", "place": "town", "rank": 1, "lat": 51.005, "lon": 1.001}


def cumulative(points):
    out = [0.0]
    for a, b in zip(points, points[1:], strict=False):
        out.append(out[-1] + haversine(a, b))
    return out


def run(elements, places=(), point=AT):
    pts = line(10)
    return describe(point, pts, cumulative(pts), list(elements), list(places))


class TestGeneric:
    def test_planner_defaults_are_generic(self):
        for name in ("Waypoint", "WPT001", "wp 12", "Point 3", "", None, "7", "via"):
            assert is_generic(name), name

    def test_a_typed_name_is_not(self):
        for name in ("172 Coffee", "Water tap", "Point Lookout", "Via Ferrata start"):
            assert not is_generic(name), name


class TestQuery:
    def test_asks_for_roads_and_features_at_every_point(self):
        q = build_query([AT, {**AT, "lat": 51.1}])
        assert q.count('way["highway"]') == 2
        assert "51.100000,1.000000" in q

    def test_asks_for_geometry_not_centres(self):
        assert "out tags geom" in build_query([AT])


class TestNearby:
    def test_a_road_split_into_several_ways_is_named_once(self):
        roads, _ = nearby(51.0045, 1.0, [road("High Street"), road("High Street", lon=1.0001)])
        assert roads == ["High Street"]

    def test_a_distant_road_is_ignored(self):
        roads, _ = nearby(51.0045, 1.0, [road("Far Lane", lon=1.01)])
        assert roads == []

    def test_irrelevant_features_are_ignored(self):
        _, feats = nearby(51.0045, 1.0, [node("SO23 41", amenity="post_box")])
        assert feats == []


class TestDescribe:
    def test_a_landmark_on_the_spot_names_it(self):
        out = run([road("High Street"), node("The Greyhound", amenity="pub")], [TOWN])
        assert out["name"] == "The Greyhound, Rye"

    def test_a_junction_names_both_roads_without_refs(self):
        out = run([road("High Street", "B3040"), road("Tower Street", lon=1.0001)], [TOWN])
        assert out["name"] == "High Street / Tower Street, Rye"
        assert "High Street (B3040)" in out["notes"]

    def test_a_named_poi_is_not_listed_as_near_itself(self):
        cafe = {**AT, "name": "172 Coffee"}
        out = run([node("172 Coffee", amenity="cafe")], point=cafe)
        assert "Nearby" not in (out["notes"] or "")

    def test_nothing_nearby_falls_back_to_distance(self):
        out = run([])
        assert out["name"] == "Route at 0.5 km"
        assert "0.5 km into the day" in out["notes"]

    def test_elevation_is_taken_from_the_route_when_missing(self):
        pts = line(10)
        for p in pts:
            p["ele"] = 120.0
        out = describe(AT, pts, cumulative(pts), [], [])
        assert out["ele"] == 120.0

    def test_off_route_distance_is_mentioned(self):
        off = {**AT, "lon": 1.005}  # ~350 m east of the line
        assert "m off the route" in run([], point=off)["notes"]

    def test_a_marker_far_from_the_day_is_not_given_a_route_position(self):
        far = {**AT, "lon": 1.05}  # ~3.5 km east
        out = run([], point=far)
        assert out["name"] == "Waypoint"
        assert "km from this day's route" in out["notes"]
        assert "into the day" not in out["notes"]


class TestSettlement:
    def test_inside_a_town_beats_a_nearer_hamlet_beyond_it(self):
        hamlet = {"name": "Nook", "place": "hamlet", "rank": 3, "lat": 51.0046, "lon": 1.0}
        town = {**TOWN, "lat": 51.012}
        found, inside = settlement(51.0045, 1.004, [hamlet, town])
        assert found["name"] == "Rye" and inside

    def test_nothing_within_reach_is_none(self):
        assert settlement(51.0, 1.0, [{**TOWN, "lat": 52.0}]) is None
