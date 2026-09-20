"""How many places a briefing names, and which ones it keeps.

A day through Kent turned up 76 settlements, which is a gazetteer rather than a
briefing. The rule is one per stretch of route - but which one matters: dropping
Rye in favour of a hamlet that happened to come first would be worse than
listing both.
"""

from app.briefing import _spaced_out

RANKS = {"city": 0, "town": 1, "village": 2, "hamlet": 3}


def place(name: str, at_km: float, kind: str = "village", distance_m: float = 50.0) -> dict:
    return {
        "name": name,
        "place": kind,
        "rank": RANKS[kind],
        "at_km": at_km,
        "distance_m": distance_m,
        "lat": 51.0,
        "lon": 1.0,
        "at_index": int(at_km * 10),
    }


class TestSpacing:
    def test_nothing_is_dropped_when_places_are_far_apart(self):
        places = [place("A", 0.0), place("B", 12.0), place("C", 25.0)]
        assert [p["name"] for p in _spaced_out(places, 10.0)] == ["A", "B", "C"]

    def test_a_cluster_collapses_to_one(self):
        places = [place(n, km) for n, km in [("A", 0.0), ("B", 1.0), ("C", 2.0), ("D", 3.0)]]
        assert len(_spaced_out(places, 10.0)) == 1

    def test_the_larger_settlement_wins_its_window(self):
        # Rye must survive even though two hamlets come first.
        places = [
            place("Hamlet one", 51.0, "hamlet"),
            place("Hamlet two", 53.0, "hamlet"),
            place("Rye", 56.3, "town"),
            place("Hamlet three", 59.5, "hamlet"),
        ]
        assert [p["name"] for p in _spaced_out(places, 10.0)] == ["Rye"]

    def test_a_tie_on_size_goes_to_the_closer_one(self):
        places = [place("Far", 1.0, "village", 90.0), place("Near", 2.0, "village", 10.0)]
        assert [p["name"] for p in _spaced_out(places, 10.0)] == ["Near"]

    def test_the_spacing_holds_across_a_window_boundary(self):
        # 9.9 and 10.1 km fall in different buckets but are 200 m apart.
        places = [place("A", 9.9), place("B", 10.1)]
        assert len(_spaced_out(places, 10.0)) == 1

    def test_a_town_just_over_a_boundary_displaces_a_village(self):
        places = [place("Village", 9.9, "village"), place("Town", 10.1, "town")]
        assert [p["name"] for p in _spaced_out(places, 10.0)] == ["Town"]

    def test_results_stay_in_route_order(self):
        places = [place("A", 0.0), place("B", 15.0), place("C", 30.0), place("D", 45.0)]
        out = _spaced_out(places, 10.0)
        assert [p["at_km"] for p in out] == sorted(p["at_km"] for p in out)

    def test_zero_spacing_keeps_everything(self):
        places = [place("A", 0.0), place("B", 0.5)]
        assert len(_spaced_out(places, 0)) == 2

    def test_a_long_day_is_trimmed_to_roughly_one_per_window(self):
        places = [place(f"P{i}", i * 1.3) for i in range(80)]  # ~103 km of places
        out = _spaced_out(places, 10.0)
        assert len(out) <= 12, f"expected about one per 10 km, got {len(out)}"
