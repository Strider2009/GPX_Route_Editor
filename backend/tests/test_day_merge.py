"""Merging a day must not quietly take its attachments with it.

The rest of the suite is pure route maths, but this one needs a session: the bug
it guards against was an ORM cascade, invisible at the maths level. Reassigning
a child's day_id looks like reparenting and passes review, yet the child stays in
the old day's collection and delete-orphan removes it when that day goes.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, Connector, Day, Poi, Project
from app.routers.days import merge_days
from app.schemas import MergeRequest


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _line(lat0: float, n: int = 5) -> list[dict]:
    return [{"lat": lat0 + 0.001 * i, "lon": 1.0, "ele": None, "time": None} for i in range(n)]


@pytest.fixture
def two_days(db):
    """Two consecutive days that meet, the second carrying a connector and a POI."""
    project = Project(name="Trip")
    db.add(project)
    db.flush()

    first = Day(project_id=project.id, name="A", order_index=0, points=_line(51.0))
    second = Day(project_id=project.id, name="B", order_index=1, points=_line(51.004))
    db.add_all([first, second])
    db.flush()

    db.add(Connector(day_id=second.id, name="Cafe spur", type="spur", points=_line(51.006, 2)))
    db.add(Poi(day_id=second.id, name="North cafe", lat=51.005, lon=1.0))
    db.add(Poi(day_id=first.id, name="South cafe", lat=51.001, lon=1.0))
    db.commit()
    return first, second


class TestMergeKeepsAttachments:
    def test_the_second_days_connector_survives(self, db, two_days):
        first, second = two_days
        merged = merge_days(MergeRequest(day_id_a=first.id, day_id_b=second.id), db)
        assert [c["name"] for c in merged["connectors"]] == ["Cafe spur"]

    def test_both_days_pois_survive(self, db, two_days):
        first, second = two_days
        merged = merge_days(MergeRequest(day_id_a=first.id, day_id_b=second.id), db)
        assert sorted(p["name"] for p in merged["pois"]) == ["North cafe", "South cafe"]

    def test_nothing_is_left_orphaned_in_the_table(self, db, two_days):
        first, second = two_days
        merge_days(MergeRequest(day_id_a=first.id, day_id_b=second.id), db)
        assert db.query(Poi).count() == 2
        assert db.query(Connector).count() == 1

    def test_the_merge_still_works_the_other_way_round(self, db, two_days):
        # Order of the arguments must not decide which day's attachments live.
        first, second = two_days
        merged = merge_days(MergeRequest(day_id_a=second.id, day_id_b=first.id), db)
        assert sorted(p["name"] for p in merged["pois"]) == ["North cafe", "South cafe"]
        assert [c["name"] for c in merged["connectors"]] == ["Cafe spur"]
