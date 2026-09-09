"""Boundary pairing and the loop wrap.

Two shipped bugs came from the same blind spot: code that paired up *consecutive*
days and so silently ignored the boundary where the last day meets the first on a
loop. Once as `set_day_edge` falling through to a destructive trim, once as
`shift_all_boundaries` rotating every join except that one. These tests pin the
wrap down in both directions.
"""

import types

import pytest
from conftest import cut, line, ring

from app.geo import cumulative_distance, haversine
from app.routers import boundaries as B


def fake_day(points, *, name="d", locked=False, lock_start=False, lock_end=False):
    """A stand-in for the ORM model - these helpers only read attributes."""
    return types.SimpleNamespace(
        id=id(points) % 10000,
        name=name,
        points=points,
        is_locked=locked,
        lock_start=lock_start,
        lock_end=lock_end,
    )


def loop_days(parts=4, n=240):
    return [fake_day(p, name=f"day{i}") for i, p in enumerate(cut(ring(n), parts))]


def line_days(parts=3, n=300):
    return [fake_day(p, name=f"day{i}") for i, p in enumerate(cut(line(n), parts))]


class TestLoopDetection:
    def test_closed_route_is_a_loop(self):
        assert B.is_loop(loop_days()) is True

    def test_point_to_point_is_not(self):
        assert B.is_loop(line_days()) is False

    def test_single_day_is_never_a_loop(self):
        assert B.is_loop([fake_day(ring(120))]) is False


class TestBoundaryPairs:
    def test_loop_has_one_boundary_per_day(self):
        days = loop_days(4)
        assert len(B.boundary_pairs(days)) == 4

    def test_point_to_point_has_one_fewer(self):
        days = line_days(3)
        assert len(B.boundary_pairs(days)) == 2

    def test_the_extra_pair_wraps_last_to_first(self):
        days = loop_days(4)
        a, b = B.boundary_pairs(days)[-1]
        assert (a.name, b.name) == ("day3", "day0")


class TestShiftAllBoundaries:
    """Shifting every boundary on a loop should rotate it, not resize the days."""

    @staticmethod
    def shift(days, delta):
        """Calls the shipped implementation, not a copy of it."""
        applied, _moved_total, _skipped = B.shift_days(days, delta)
        return applied

    def test_every_boundary_moves_including_the_wrap(self):
        days = loop_days(4)
        assert self.shift(days, 2000) == 4

    def test_the_first_days_start_actually_moves(self):
        days = loop_days(4)
        before = dict(days[0].points[0])
        self.shift(days, 2000)
        assert haversine(before, days[0].points[0]) > 500

    def test_the_last_days_end_moves_with_it(self):
        days = loop_days(4)
        before = dict(days[-1].points[-1])
        self.shift(days, 2000)
        assert haversine(before, days[-1].points[-1]) > 500

    def test_first_start_and_last_end_stay_the_same_point(self):
        days = loop_days(4)
        self.shift(days, 2000)
        assert haversine(days[-1].points[-1], days[0].points[0]) < 1.0

    def test_day_lengths_are_preserved(self):
        """The whole point of a shift: rotate the loop, don't resize the days."""
        days = loop_days(4)
        before = [cumulative_distance(d.points) for d in days]
        self.shift(days, 2000)
        after = [cumulative_distance(d.points) for d in days]
        for was, now in zip(before, after, strict=False):
            assert now == pytest.approx(was, abs=250)

    def test_the_loop_stays_closed(self):
        days = loop_days(4)
        self.shift(days, 2000)
        assert B.is_loop(days) is True

    def test_all_joins_survive(self):
        days = loop_days(4)
        self.shift(days, 2000)
        for a, b in B.boundary_pairs(days):
            assert B._joins(a, b) is True

    def test_shifting_back_returns_roughly_home(self):
        days = loop_days(4)
        before = dict(days[0].points[0])
        self.shift(days, 2000)
        self.shift(days, -2000)
        # Boundaries snap to real points, so expect near-identity, not identity.
        assert haversine(before, days[0].points[0]) < 150

    def test_a_point_to_point_route_leaves_its_outer_ends_alone(self):
        """There is no day to hand points to, so the trip's ends cannot move."""
        days = line_days(3)
        first, last = dict(days[0].points[0]), dict(days[-1].points[-1])
        self.shift(days, 2000)
        assert haversine(first, days[0].points[0]) < 1.0
        assert haversine(last, days[-1].points[-1]) < 1.0


class TestBlockers:
    def test_a_locked_day_freezes_its_boundary(self):
        a, b = loop_days(2)
        a.is_locked = True
        assert B._blockers(a, b)

    def test_a_pinned_end_freezes_it_too(self):
        a, b = loop_days(2)
        a.lock_end = True
        assert B._blockers(a, b)

    def test_a_pinned_start_on_the_later_day_freezes_it(self):
        a, b = loop_days(2)
        b.lock_start = True
        assert B._blockers(a, b)

    def test_days_that_do_not_meet_cannot_be_slid(self):
        a = fake_day(line(50))
        b = fake_day(line(50, lat0=60.0))  # a long way north
        assert "don't join end to end" in " ".join(B._blockers(a, b))

    def test_an_unobstructed_boundary_has_no_blockers(self):
        a, b = loop_days(2)
        assert B._blockers(a, b) == []

    def test_a_locked_day_is_skipped_rather_than_erroring(self):
        days = loop_days(4)
        days[1].is_locked = True
        moved = TestShiftAllBoundaries.shift(days, 2000)
        # Both boundaries touching the locked day hold; the other two still move.
        assert moved == 2
