from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    source_filename: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    days: Mapped[list["Day"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Day.order_index"
    )


class Day(Base):
    __tablename__ = "days"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    is_circular: Mapped[bool] = mapped_column(Boolean, default=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    # Pin just one end in place: the shared boundary with the neighbouring day
    # can then only move if both sides allow it.
    lock_start: Mapped[bool] = mapped_column(Boolean, default=False)
    lock_end: Mapped[bool] = mapped_column(Boolean, default=False)
    # Ordered list of {lat, lon, ele, time} dicts - the "core" route for this day.
    points: Mapped[list] = mapped_column(JSON, default=list)
    # The route this day was carved from, kept so trimming can be undone and the
    # discarded ends can still be shown and reselected. Only trimming preserves
    # it; every other edit rebaselines it to the current points.
    source_points: Mapped[list] = mapped_column(JSON, default=list)

    project: Mapped["Project"] = relationship(back_populates="days")
    connectors: Mapped[list["Connector"]] = relationship(
        back_populates="day", cascade="all, delete-orphan"
    )


class Roadwork(Base):
    """A roadworks/closure record imported from a vector tile the user supplied.

    Nothing in the app fetches these - tiles are saved by hand and uploaded.
    """

    __tablename__ = "roadworks"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_roadwork_source_external"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String, index=True)
    source: Mapped[str] = mapped_column(String, default="tile-import")
    layer: Mapped[str | None] = mapped_column(String, nullable=True)

    road_name: Mapped[str | None] = mapped_column(String, nullable=True)
    works_desc: Mapped[str | None] = mapped_column(String, nullable=True)
    resporg_name: Mapped[str | None] = mapped_column(String, nullable=True)
    pub_name: Mapped[str | None] = mapped_column(String, nullable=True)
    permit_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    works_ref: Mapped[str | None] = mapped_column(String, nullable=True)

    # Tiles carry this as a readable label ("Road closure"), not the integer code
    # that the filter API uses.
    traffic_management: Mapped[str | None] = mapped_column(String, nullable=True)
    delay: Mapped[str | None] = mapped_column(String, nullable=True)
    tm_cat: Mapped[str | None] = mapped_column(String, nullable=True)
    item_type: Mapped[str | None] = mapped_column(String, nullable=True)
    impact: Mapped[int | None] = mapped_column(Integer, nullable=True)
    works_state: Mapped[int | None] = mapped_column(Integer, nullable=True)
    permit_status: Mapped[int | None] = mapped_column(Integer, nullable=True)

    start_date: Mapped[str | None] = mapped_column(String, nullable=True)
    end_date: Mapped[str | None] = mapped_column(String, nullable=True)

    # [[lat, lon], ...] plus a bounding box for cheap pre-filtering.
    geometry: Mapped[list] = mapped_column(JSON, default=list)
    min_lat: Mapped[float] = mapped_column(Float, default=0.0)
    max_lat: Mapped[float] = mapped_column(Float, default=0.0)
    min_lon: Mapped[float] = mapped_column(Float, default=0.0)
    max_lon: Mapped[float] = mapped_column(Float, default=0.0)

    attrs: Mapped[dict] = mapped_column(JSON, default=dict)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class Pothole(Base):
    """A pothole report from FixMyStreet, stored by its report id."""

    __tablename__ = "potholes"
    __table_args__ = (UniqueConstraint("source", "report_id", name="uq_pothole_source_report"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[str] = mapped_column(String, index=True)
    source: Mapped[str] = mapped_column(String, default="fixmystreet")
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    colour: Mapped[str | None] = mapped_column(String, nullable=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class PotholeArea(Base):
    """Which boxes have been asked about, so a repeat check doesn't re-request them."""

    __tablename__ = "pothole_areas"
    __table_args__ = (UniqueConstraint("box", name="uq_pothole_area_box"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    box: Mapped[str] = mapped_column(String, index=True)
    pin_count: Mapped[int] = mapped_column(Integer, default=0)
    saturated: Mapped[bool] = mapped_column(Boolean, default=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class StravaAuth(Base):
    """The connected Strava athlete. Single-athlete tool, so at most one row.

    Only tokens live here - the client secret stays in the environment.
    """

    __tablename__ = "strava_auth"

    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    athlete_name: Mapped[str | None] = mapped_column(String, nullable=True)
    access_token: Mapped[str] = mapped_column(String)
    refresh_token: Mapped[str] = mapped_column(String)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    scope: Mapped[str | None] = mapped_column(String, nullable=True)
    connected_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class HistorySnapshot(Base):
    """One step of undo/redo: a compressed snapshot of a project's days."""

    __tablename__ = "history_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[str] = mapped_column(String, index=True)  # "undo" | "redo"
    action: Mapped[str] = mapped_column(String)
    state: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class TileCache(Base):
    """Raw tiles kept as fetched, so a repeat check costs no requests.

    Keyed by date as well as position: the tile server filters works by the date
    range asked for, so the same square differs between dates.
    """

    __tablename__ = "tile_cache"
    __table_args__ = (UniqueConstraint("z", "x", "y", "target_date", name="uq_tile_cache_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    z: Mapped[int] = mapped_column(Integer)
    x: Mapped[int] = mapped_column(Integer)
    y: Mapped[int] = mapped_column(Integer)
    target_date: Mapped[str] = mapped_column(String, index=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    byte_size: Mapped[int] = mapped_column(Integer, default=0)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class Connector(Base):
    """A navigation leg attached to a Day that is never affected by the day's lock.

    type is one of: start_access, end_access, spur.
    """

    __tablename__ = "connectors"

    id: Mapped[int] = mapped_column(primary_key=True)
    day_id: Mapped[int] = mapped_column(ForeignKey("days.id"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    points: Mapped[list] = mapped_column(JSON, default=list)

    day: Mapped["Day"] = relationship(back_populates="connectors")
