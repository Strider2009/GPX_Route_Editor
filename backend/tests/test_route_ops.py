"""Invariants for the core route operations."""

import pytest
from conftest import cut, line, ring

from app import route_ops
from app.geo import cumulative_distance, haversine


class TestRotate:
    def test_loop_reopens_at_the_chosen_point(self):
        pts = ring(120)
        rotated = route_ops.rotate_to_start(pts, 30)
        assert rotated[0]["lat"] == pytest.approx(pts[30]["lat"])
        assert rotated[0]["lon"] == pytest.approx(pts[30]["lon"])

    def test_loop_stays_closed(self):
        rotated = route_ops.rotate_to_start(ring(120), 30)
        assert haversine(rotated[0], rotated[-1]) < 1.0

    def test_length_is_preserved(self):
        pts = ring(120)
        rotated = route_ops.rotate_to_start(pts, 47)
        assert cumulative_distance(rotated) == pytest.approx(cumulative_distance(pts), rel=1e-6)


class TestTrimAndReverse:
    def test_trim_is_inclusive_at_both_ends(self):
        pts = line(50)
        assert len(route_ops.trim(pts, 10, 20)) == 11

    def test_reverse_round_trips(self):
        pts = line(20)
        assert route_ops.reverse(route_ops.reverse(pts)) == pts

    def test_reverse_keeps_length(self):
        pts = line(20)
        assert cumulative_distance(route_ops.reverse(pts)) == pytest.approx(
            cumulative_distance(pts)
        )


class TestSplit:
    def test_adjacent_days_share_exactly_one_point(self):
        parts = route_ops.split(line(100), [40])
        assert parts[0][-1] == parts[1][0]

    def test_no_ground_is_lost(self):
        pts = line(100)
        parts = route_ops.split(pts, [30, 60])
        total = sum(cumulative_distance(p) for p in parts)
        assert total == pytest.approx(cumulative_distance(pts), rel=1e-9)

    def test_even_split_produces_similar_lengths(self):
        pts = line(400)
        idx = route_ops.even_split_indices(pts, 4)
        parts = route_ops.split(pts, idx)
        lengths = [cumulative_distance(p) for p in parts]
        assert max(lengths) - min(lengths) < 0.05 * max(lengths)


class TestMoveBoundary:
    """The shared-boundary contract: one point, moved, never duplicated or lost."""

    def test_forward_lengthens_the_earlier_day(self):
        a, b = cut(line(200), 2)
        before = cumulative_distance(a)
        new_a, _, moved = route_ops.move_boundary(a, b, 2000)
        assert moved > 0
        assert cumulative_distance(new_a) > before

    def test_backward_shortens_the_earlier_day(self):
        a, b = cut(line(200), 2)
        before = cumulative_distance(a)
        new_a, _, moved = route_ops.move_boundary(a, b, -2000)
        assert moved < 0
        assert cumulative_distance(new_a) < before

    @pytest.mark.parametrize("delta", [3000, -3000])
    def test_days_still_share_one_point(self, delta):
        a, b = cut(line(200), 2)
        new_a, new_b, _ = route_ops.move_boundary(a, b, delta)
        assert new_a[-1]["lat"] == pytest.approx(new_b[0]["lat"])
        assert new_a[-1]["lon"] == pytest.approx(new_b[0]["lon"])

    @pytest.mark.parametrize("delta", [3000, -3000])
    def test_total_distance_is_conserved(self, delta):
        a, b = cut(line(200), 2)
        before = cumulative_distance(a) + cumulative_distance(b)
        new_a, new_b, _ = route_ops.move_boundary(a, b, delta)
        after = cumulative_distance(new_a) + cumulative_distance(new_b)
        assert after == pytest.approx(before, rel=1e-6)

    def test_never_shrinks_a_day_below_the_minimum(self):
        a, b = cut(line(100), 2)
        # Far more than the day could ever give up.
        new_a, new_b, _ = route_ops.move_boundary(a, b, 10_000_000)
        assert len(new_a) >= route_ops.MIN_DAY_POINTS
        assert len(new_b) >= route_ops.MIN_DAY_POINTS

    def test_refuses_to_move_when_the_neighbour_is_already_minimal(self):
        a, b = line(50), line(route_ops.MIN_DAY_POINTS)
        new_a, new_b, moved = route_ops.move_boundary(a, b, 500)
        assert moved == 0
        assert (new_a, new_b) == (a, b)

    def test_move_is_bounded_by_the_reported_range(self):
        a, b = cut(line(200), 2)
        _, forward = route_ops.boundary_range(a, b)
        _, _, moved = route_ops.move_boundary(a, b, forward + 5000)
        assert moved <= forward + 1e-6
