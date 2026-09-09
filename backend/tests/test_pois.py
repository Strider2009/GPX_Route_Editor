"""Invariants for POI export and import.

Kept to the GPX layer for the same reason as the rest of the suite: that is
where a bug would silently cost you the markers, either by writing a file a
device won't read or by dropping fields on the way back in.
"""

from conftest import line

from app.gpx_io import build_gpx, day_export_waypoints, parse_gpx, parse_waypoints

CAFE = {
    "name": "Coffee stop",
    "lat": 51.0005,
    "lon": 1.0005,
    "ele": 42.0,
    "symbol": "Restaurant",
    "notes": "Opens at 08:00",
}
TAP = {"name": "Water tap", "lat": 51.0010, "lon": 1.0010}


class FakePoi:
    """Stands in for the ORM row; day_export_waypoints only reads attributes."""

    def __init__(self, **kw):
        self.__dict__.update({"ele": None, "symbol": None, "notes": None, **kw})


class FakeDay:
    def __init__(self, pois):
        self.pois = pois


class TestExport:
    def test_a_poi_becomes_a_top_level_wpt(self):
        xml = build_gpx("Day 1", [("Day 1", line(5))], waypoints=[CAFE]).decode()
        assert "<wpt " in xml
        assert "Coffee stop" in xml

    def test_the_wpt_carries_name_description_and_symbol(self):
        xml = build_gpx("Day 1", [("Day 1", line(5))], waypoints=[CAFE]).decode()
        assert "<name>Coffee stop</name>" in xml
        assert "<desc>Opens at 08:00</desc>" in xml
        assert "<sym>Restaurant</sym>" in xml

    def test_waypoints_are_written_before_the_track(self):
        # GPX 1.1 requires wpt, then rte, then trk. A device is entitled to
        # reject the file if they come out in any other order.
        xml = build_gpx("Day 1", [("Day 1", line(5))], waypoints=[CAFE]).decode()
        assert xml.index("<wpt ") < xml.index("<trk>")

    def test_a_day_with_no_pois_still_exports_no_wpt(self):
        xml = build_gpx("Day 1", [("Day 1", line(5))]).decode()
        assert "<wpt" not in xml

    def test_the_track_is_untouched_by_adding_a_poi(self):
        plain = parse_gpx(build_gpx("Day 1", [("Day 1", line(9))]))
        with_poi = parse_gpx(build_gpx("Day 1", [("Day 1", line(9))], waypoints=[CAFE]))
        assert plain[0]["points"] == with_poi[0]["points"]


class TestRoundTrip:
    def test_a_poi_survives_export_and_reimport(self):
        xml = build_gpx("Day 1", [("Day 1", line(5))], waypoints=[CAFE])
        back = parse_waypoints(xml)
        assert len(back) == 1
        assert back[0]["name"] == CAFE["name"]
        assert back[0]["lat"] == CAFE["lat"]
        assert back[0]["symbol"] == CAFE["symbol"]
        assert back[0]["notes"] == CAFE["notes"]

    def test_the_optional_fields_stay_empty_rather_than_inventing_values(self):
        xml = build_gpx("Day 1", [("Day 1", line(5))], waypoints=[TAP])
        back = parse_waypoints(xml)[0]
        assert back["ele"] is None
        assert back["symbol"] is None
        assert back["notes"] is None

    def test_every_poi_comes_back(self):
        xml = build_gpx("Day 1", [("Day 1", line(5))], waypoints=[CAFE, TAP])
        assert [w["name"] for w in parse_waypoints(xml)] == ["Coffee stop", "Water tap"]

    def test_a_file_with_no_waypoints_yields_none(self):
        assert parse_waypoints(build_gpx("Day 1", [("Day 1", line(5))])) == []


class TestDayExportWaypoints:
    def test_it_reads_the_days_pois(self):
        day = FakeDay([FakePoi(name="Cafe", lat=51.0, lon=1.0, symbol="Restaurant")])
        out = day_export_waypoints(day)
        assert out == [
            {
                "name": "Cafe",
                "lat": 51.0,
                "lon": 1.0,
                "ele": None,
                "symbol": "Restaurant",
                "notes": None,
            }
        ]

    def test_a_day_without_pois_contributes_nothing(self):
        assert day_export_waypoints(FakeDay([])) == []
