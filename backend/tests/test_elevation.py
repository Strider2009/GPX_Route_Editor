"""Elevation providers and what's built on them.

The network isn't exercised. What matters is that batching and de-duplication
send each provider what it expects, that filling never clobbers recorded heights
unless asked, and that the comparison scores providers on the same footing.
"""

import json

import pytest
from conftest import line

from app.elevation import providers as prov
from app.elevation.providers import ElevationError, ElevationProvider, OpenMeteo, OpenTopoData
from app.elevation.service import apply_heights, compare, coords_to_fill, fill


class FakeProvider(ElevationProvider):
    """Height = 1000 x latitude offset, so every point gets a distinct, predictable value."""

    id = "fake"
    label = "Fake"
    description = "test"
    batch_size = 3

    def __init__(self, offset: float = 0.0):
        self.offset = offset
        self.batches: list[list[tuple[float, float]]] = []

    def _host(self) -> str:
        return "fake"

    def _fetch_batch(self, coords):
        self.batches.append(coords)
        return [round((lat - 51.0) * 1000 + self.offset, 3) for lat, _ in coords]


class TestLookup:
    def test_batches_respect_the_provider_limit(self):
        p = FakeProvider()
        p.lookup([(51.0 + i * 0.001, 1.0) for i in range(7)])
        assert [len(b) for b in p.batches] == [3, 3, 1]

    def test_repeated_coordinates_are_looked_up_once_but_answered_everywhere(self):
        p = FakeProvider()
        out = p.lookup([(51.001, 1.0), (51.002, 1.0), (51.001, 1.0)])
        assert sum(len(b) for b in p.batches) == 2
        assert out[0] == out[2]

    def test_unknown_provider_is_an_error(self):
        with pytest.raises(ElevationError):
            prov.get_provider("nope")


class FakeResponse:
    def __init__(self, body: str):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.body.encode()


class TestParsing:
    def test_open_meteo_reads_nan_as_missing(self, monkeypatch):
        seen = []

        def fake(req, timeout):
            seen.append(req.full_url)
            return FakeResponse('{"elevation": [12.5, NaN]}')

        monkeypatch.setattr(prov.http_client, "urlopen", fake)
        assert OpenMeteo(base="https://example.test/v1/elevation").lookup(
            [(51.0, 1.0), (52.0, 2.0)]
        ) == [12.5, None]
        assert "latitude=51.000000%2C52.000000" in seen[0]

    def test_opentopodata_reads_results_in_order(self, monkeypatch):
        body = {"status": "OK", "results": [{"elevation": 63.4}, {"elevation": None}]}
        monkeypatch.setattr(
            prov.http_client, "urlopen", lambda req, timeout: FakeResponse(json.dumps(body))
        )
        p = OpenTopoData("eudem25m", "EU-DEM", "", base="https://example.test/v1")
        p.min_interval_s = 0
        assert p.lookup([(51.0, 1.0), (52.0, 2.0)]) == [63.4, None]

    def test_opentopodata_error_status_is_raised(self, monkeypatch):
        body = {"status": "INVALID_REQUEST", "error": "Too many locations"}
        monkeypatch.setattr(
            prov.http_client, "urlopen", lambda req, timeout: FakeResponse(json.dumps(body))
        )
        p = OpenTopoData("eudem25m", "EU-DEM", "", base="https://example.test/v1")
        p.min_interval_s = 0
        with pytest.raises(ElevationError, match="Too many locations"):
            p.lookup([(51.0, 1.0)])


class TestFill:
    def test_only_gaps_are_filled_by_default(self):
        pts = line(5)
        pts[2]["ele"] = 999.0
        assert fill([pts], FakeProvider()) == 4
        assert pts[2]["ele"] == 999.0
        assert all(p["ele"] is not None for p in pts)

    def test_overwrite_replaces_recorded_heights(self):
        pts = line(5)
        pts[2]["ele"] = 999.0
        fill([pts], FakeProvider(), overwrite=True)
        assert pts[2]["ele"] != 999.0

    def test_a_route_that_already_has_heights_costs_no_requests(self):
        pts = [{**p, "ele": 1.0} for p in line(5)]
        p = FakeProvider()
        assert fill([pts], p) == 0
        assert p.batches == []


class TestCompare:
    def test_a_provider_matching_the_recording_scores_zero(self):
        pts = line(20)
        fill([pts], FakeProvider())
        out = compare(pts, [FakeProvider()], samples=10)
        stats = out["providers"][0]["stats"]
        assert stats["mae_m"] == 0 and stats["bias_m"] == 0
        assert out["providers"][0]["profile"]["ascent_m"] == out["recorded"]["ascent_m"]

    def test_a_constant_offset_shows_as_bias(self):
        pts = line(20)
        fill([pts], FakeProvider())
        stats = compare(pts, [FakeProvider(offset=5)], samples=10)["providers"][0]["stats"]
        assert stats["bias_m"] == 5 and stats["rmse_m"] == 5

    def test_samples_keep_both_ends(self):
        out = compare(line(50), [FakeProvider()], samples=7)
        assert out["samples"][0]["index"] == 0 and out["samples"][-1]["index"] == 49

    def test_without_recorded_heights_there_is_nothing_to_score_against(self):
        out = compare(line(10), [FakeProvider()])
        assert out["recorded"] is None and out["providers"][0]["stats"] is None

    def test_one_failing_provider_does_not_sink_the_rest(self):
        class Broken(FakeProvider):
            id = "broken"

            def _fetch_batch(self, coords):
                raise ElevationError("down")

        out = compare(line(10), [Broken(), FakeProvider()])
        assert out["providers"][0]["error"] == "down"
        assert out["providers"][1]["heights"]


class TestRateLimits:
    def test_a_rate_limited_batch_is_retried(self):
        class Flaky(FakeProvider):
            retry_after_s = 0
            calls = 0

            def _fetch_batch(self, coords):
                self.calls += 1
                if self.calls == 1:
                    raise prov.RateLimited("slow down")
                return super()._fetch_batch(coords)

        p = Flaky()
        assert p.lookup([(51.001, 1.0)]) == [1.0]
        assert p.calls == 2

    def test_a_provider_that_never_relents_gives_up(self):
        class Stubborn(FakeProvider):
            retry_after_s = 0

            def _fetch_batch(self, coords):
                raise prov.RateLimited("slow down")

        with pytest.raises(prov.RateLimited):
            Stubborn().lookup([(51.001, 1.0)])

    def test_a_points_per_minute_budget_makes_the_next_batch_wait(self, monkeypatch):
        clock = [1000.0]
        slept = []

        def sleep(s):
            slept.append(s)
            clock[0] += s

        monkeypatch.setattr(prov.time, "monotonic", lambda: clock[0])
        monkeypatch.setattr(prov.time, "sleep", sleep)
        limiter = prov._HostLimiter()
        limiter.wait(80, 0, 100)
        limiter.wait(80, 0, 100)
        assert slept and sum(slept) >= 60

    def test_progress_reports_each_batch(self):
        seen = []
        FakeProvider().lookup(
            [(51.0 + i * 0.001, 1.0) for i in range(7)], lambda d, t: seen.append((d, t))
        )
        assert seen == [(3, 7), (6, 7), (7, 7)]


class TestApplyByLocation:
    def test_heights_land_on_a_route_edited_while_they_were_fetched(self):
        pts = line(5)
        coords = coords_to_fill([pts])
        heights = dict(zip(coords, FakeProvider().lookup(coords), strict=True))
        edited = [pts[0], pts[3], pts[4]]  # two points deleted meanwhile
        assert apply_heights([edited], heights) == 3
        assert all(p["ele"] is not None for p in edited)

    def test_a_point_added_meanwhile_is_left_without_a_height(self):
        heights = {}
        added = [{"lat": 52.0, "lon": 2.0, "ele": None, "time": None}]
        assert apply_heights([added], heights) == 0
