"""Invariants for venue discovery.

The network call itself isn't tested - the parts worth pinning down are the
query we send (a malformed one wastes somebody's donated server) and the
filtering of what comes back.
"""

from app import overpass_fetch
from app.overpass_fetch import KINDS, build_query, search


class TestQuery:
    def test_every_kind_contributes_a_clause(self):
        q = build_query(51.0, -2.5, 1000, ["cafe", "water"])
        assert q.count("nwr") == len(KINDS["cafe"]) + len(KINDS["water"])

    def test_the_radius_and_point_are_in_the_query(self):
        q = build_query(51.4545, -2.5879, 750, ["cafe"])
        assert "around:750,51.454500,-2.587900" in q

    def test_it_asks_for_centres_so_ways_and_relations_have_a_point(self):
        assert "out center" in build_query(51.0, -2.5, 500, ["cafe"])

    def test_an_unknown_kind_produces_no_clauses(self):
        assert "nwr" not in build_query(51.0, -2.5, 500, ["spaceport"])


class TestParsing:
    def _run(self, monkeypatch, elements):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                import json

                return json.dumps({"elements": elements}).encode()

        monkeypatch.setattr(overpass_fetch.http_client, "urlopen", lambda *a, **k: FakeResponse())
        return search(51.0, -2.5, 1000, ["cafe", "water"])

    def test_a_named_cafe_is_kept(self, monkeypatch):
        out = self._run(
            monkeypatch,
            [
                {
                    "type": "node",
                    "id": 1,
                    "lat": 51.0,
                    "lon": -2.5,
                    "tags": {"amenity": "cafe", "name": "Bean"},
                }
            ],
        )
        assert [(v["name"], v["kind"]) for v in out] == [("Bean", "cafe")]

    def test_an_unnamed_cafe_is_dropped_but_unnamed_water_is_not(self, monkeypatch):
        out = self._run(
            monkeypatch,
            [
                {"type": "node", "id": 1, "lat": 51.0, "lon": -2.5, "tags": {"amenity": "cafe"}},
                {
                    "type": "node",
                    "id": 2,
                    "lat": 51.0,
                    "lon": -2.5,
                    "tags": {"amenity": "drinking_water"},
                },
            ],
        )
        assert [v["kind"] for v in out] == ["water"]

    def test_a_way_uses_its_centre_point(self, monkeypatch):
        out = self._run(
            monkeypatch,
            [
                {
                    "type": "way",
                    "id": 9,
                    "center": {"lat": 51.1, "lon": -2.4},
                    "tags": {"amenity": "cafe", "name": "W"},
                }
            ],
        )
        assert (out[0]["lat"], out[0]["lon"], out[0]["external_id"]) == (51.1, -2.4, "way/9")

    def test_only_useful_tags_are_kept(self, monkeypatch):
        out = self._run(
            monkeypatch,
            [
                {
                    "type": "node",
                    "id": 1,
                    "lat": 51.0,
                    "lon": -2.5,
                    "tags": {
                        "amenity": "cafe",
                        "name": "B",
                        "opening_hours": "Mo-Fr 08:00-17:00",
                        "fixme": "junk",
                        "source": "survey",
                    },
                }
            ],
        )
        assert out[0]["tags"] == {"opening_hours": "Mo-Fr 08:00-17:00"}

    def test_a_kind_that_was_not_asked_for_is_dropped(self, monkeypatch):
        out = self._run(
            monkeypatch,
            [
                {
                    "type": "node",
                    "id": 1,
                    "lat": 51.0,
                    "lon": -2.5,
                    "tags": {"amenity": "pub", "name": "P"},
                }
            ],
        )
        assert out == []

    def test_duplicates_are_collapsed(self, monkeypatch):
        el = {
            "type": "node",
            "id": 1,
            "lat": 51.0,
            "lon": -2.5,
            "tags": {"amenity": "cafe", "name": "B"},
        }
        assert len(self._run(monkeypatch, [el, dict(el)])) == 1


class TestUsability:
    """Things OSM records that would be misleading to list."""

    def _run(self, monkeypatch, elements, kinds=("water",)):
        import json

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return json.dumps({"elements": elements}).encode()

        monkeypatch.setattr(overpass_fetch.http_client, "urlopen", lambda *a, **k: FakeResponse())
        return search(51.0, -2.5, 1000, list(kinds))

    def _node(self, **tags):
        return {"type": "node", "id": 1, "lat": 51.0, "lon": -2.5, "tags": tags}

    def test_non_potable_tap_is_dropped(self, monkeypatch):
        # Real data: man_made=water_tap with drinking_water=no exists in OSM, and
        # listing it would send you to fill a bottle from it.
        out = self._run(monkeypatch, [self._node(man_made="water_tap", drinking_water="no")])
        assert out == []

    def test_legally_non_potable_is_dropped(self, monkeypatch):
        out = self._run(
            monkeypatch,
            [self._node(**{"man_made": "water_tap", "drinking_water:legal": "no"})],
        )
        assert out == []

    def test_a_private_tap_is_dropped(self, monkeypatch):
        out = self._run(monkeypatch, [self._node(amenity="drinking_water", access="private")])
        assert out == []

    def test_a_disused_fountain_is_dropped(self, monkeypatch):
        out = self._run(
            monkeypatch,
            [self._node(**{"amenity": "drinking_water", "disused:amenity": "drinking_water"})],
        )
        assert out == []

    def test_a_plain_drinking_water_point_survives(self, monkeypatch):
        out = self._run(monkeypatch, [self._node(amenity="drinking_water")])
        assert len(out) == 1

    def test_the_fountain_type_is_kept_because_it_is_the_useful_bit(self, monkeypatch):
        out = self._run(
            monkeypatch, [self._node(amenity="drinking_water", fountain="bottle_refill", fee="no")]
        )
        assert out[0]["tags"]["fountain"] == "bottle_refill"
        assert out[0]["tags"]["fee"] == "no"

    def test_an_untyped_tap_is_labelled_rather_than_left_blank(self, monkeypatch):
        out = self._run(monkeypatch, [self._node(man_made="water_tap", drinking_water="yes")])
        assert out[0]["tags"]["fountain"] == "tap"

    def test_an_address_is_composed_into_one_line(self, monkeypatch):
        out = self._run(
            monkeypatch,
            [
                {
                    "type": "node",
                    "id": 2,
                    "lat": 51.0,
                    "lon": -2.5,
                    "tags": {
                        "amenity": "cafe",
                        "name": "Bean",
                        "addr:housenumber": "12",
                        "addr:street": "High St",
                        "addr:postcode": "BS1 1AA",
                    },
                }
            ],
            kinds=("cafe",),
        )
        assert out[0]["tags"]["address"] == "12 High St, BS1 1AA"

    def test_a_closed_cafe_is_dropped(self, monkeypatch):
        out = self._run(
            monkeypatch,
            [
                {
                    "type": "node",
                    "id": 3,
                    "lat": 51.0,
                    "lon": -2.5,
                    "tags": {"amenity": "cafe", "name": "Gone", "operational_status": "closed"},
                }
            ],
            kinds=("cafe",),
        )
        assert out == []
