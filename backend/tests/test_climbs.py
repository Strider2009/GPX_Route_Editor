"""Invariants for climb detection.

Built on synthetic profiles because the failure mode that matters is silent: a
detector that turns GPS noise into climbs makes every flat ride look lumpy, and
one that smooths too hard loses the climb you needed to know about.
"""

import pytest
from conftest import STEP

from app.climbs import categorise, find_climbs, profile_summary


def profile(elevations: list[float], lat0: float = 51.0) -> list[dict]:
    """A north-running track with the given elevations, ~100 m between points."""
    return [
        {"lat": lat0 + STEP * i, "lon": 1.0, "ele": e, "time": None}
        for i, e in enumerate(elevations)
    ]


def ramp(n: int, per_point: float, start: float = 0.0) -> list[float]:
    return [start + per_point * i for i in range(n)]


class TestDetection:
    def test_a_flat_route_has_no_climbs(self):
        assert find_climbs(profile([100.0] * 40)) == []

    def test_gps_noise_on_the_flat_is_not_a_climb(self):
        # +/- 2 m of jitter is normal and must not register.
        noisy = [100.0 + (2.0 if i % 2 else -2.0) for i in range(60)]
        assert find_climbs(profile(noisy)) == []

    def test_a_real_climb_is_found(self):
        # 30 points at 100 m spacing, 3 m up each = ~3 km at ~3%.
        pts = profile([100.0] * 5 + ramp(30, 3.0, 100.0) + [190.0] * 5)
        found = find_climbs(pts)
        assert len(found) == 1
        assert found[0]["gain_m"] == pytest.approx(87, abs=8)

    def test_the_gradient_is_about_right(self):
        pts = profile([100.0] * 5 + ramp(30, 5.0, 100.0) + [250.0] * 5)
        avg = find_climbs(pts)[0]["avg_gradient"]
        # 5 m per ~100 m of road is about 5%.
        assert avg == pytest.approx(5.0, abs=1.2)

    def test_a_short_bump_is_ignored(self):
        pts = profile([100.0] * 10 + ramp(3, 2.0, 100.0) + [106.0] * 10)
        assert find_climbs(pts) == []

    def test_two_separated_climbs_are_two_climbs(self):
        pts = profile(
            [100.0] * 5
            + ramp(25, 4.0, 100.0)
            + ramp(25, -4.0, 200.0)
            + ramp(25, 4.0, 100.0)
            + [200.0] * 5
        )
        assert len(find_climbs(pts)) == 2

    def test_a_small_dip_does_not_split_one_climb(self):
        # A 5 m false flat partway up is part of the climb, not the end of it.
        pts = profile(
            [100.0] * 3 + ramp(15, 4.0, 100.0) + [155.0, 152.0, 151.0] + ramp(15, 4.0, 151.0)
        )
        assert len(find_climbs(pts)) == 1

    def test_climbs_come_back_in_route_order(self):
        pts = profile(
            [100.0] * 5 + ramp(25, 4.0, 100.0) + ramp(25, -4.0, 200.0) + ramp(25, 6.0, 100.0)
        )
        found = find_climbs(pts)
        assert [c["start_index"] for c in found] == sorted(c["start_index"] for c in found)

    def test_a_route_without_elevation_yields_nothing(self):
        pts = [{"lat": 51.0 + STEP * i, "lon": 1.0, "ele": None, "time": None} for i in range(40)]
        assert find_climbs(pts) == []
        assert profile_summary(pts) == {"has_elevation": False}


class TestCategories:
    def test_a_gentle_rise_is_uncategorised(self):
        assert categorise(1000, 3.0) is None

    def test_the_bands_ascend_in_the_right_order(self):
        assert categorise(4000, 3.0) == "4"
        assert categorise(4000, 5.0) == "3"
        assert categorise(8000, 5.0) == "2"
        assert categorise(8000, 9.0) == "1"
        assert categorise(16000, 9.0) == "HC"

    def test_a_longer_climb_at_the_same_gradient_never_drops_a_category(self):
        order = [None, "4", "3", "2", "1", "HC"]
        previous = 0
        for length in (2000, 4000, 8000, 16000, 32000):
            rank = order.index(categorise(length, 6.0))
            assert rank >= previous
            previous = rank


class TestRollingTerrain:
    """The case that a purely absolute dip threshold gets wrong.

    Kent gave a real example: 97 km with 1,035 m of ascent reported zero climbs,
    because each 10 m dip was under the absolute threshold, so a long series of
    rollers accumulated into one segment too shallow to qualify.
    """

    def _rollers(self, count: int, up: float, down: float) -> list[float]:
        eles = [50.0]
        for _ in range(count):
            for _ in range(8):
                eles.append(eles[-1] + up / 8)
            for _ in range(6):
                eles.append(eles[-1] - down / 6)
        return eles

    def test_a_series_of_rollers_is_not_one_giant_climb(self):
        found = find_climbs(profile(self._rollers(5, 35.0, 12.0)))
        assert len(found) >= 3, f"expected several rollers, got {len(found)}"

    def test_each_roller_is_measured_separately(self):
        found = find_climbs(profile(self._rollers(4, 40.0, 14.0)))
        # None should span the whole route; each is one roller.
        assert all(c["gain_m"] < 80 for c in found)

    def test_a_genuine_single_climb_is_still_one_climb(self):
        # The relative rule must not shatter a real climb with a false flat in it.
        eles = [100.0] * 3 + ramp(20, 5.0, 100.0) + [199.0, 197.0] + ramp(20, 5.0, 197.0)
        assert len(find_climbs(profile(eles))) == 1
