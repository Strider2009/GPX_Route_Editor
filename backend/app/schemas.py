from pydantic import BaseModel


class PointSchema(BaseModel):
    lat: float
    lon: float
    ele: float | None = None
    time: str | None = None


class ConnectorCreate(BaseModel):
    name: str
    type: str
    points: list[PointSchema] = []


class ConnectorUpdate(BaseModel):
    name: str | None = None
    points: list[PointSchema] | None = None


class PoiCreate(BaseModel):
    name: str
    lat: float
    lon: float
    ele: float | None = None
    symbol: str | None = None
    notes: str | None = None


class PoiUpdate(BaseModel):
    name: str | None = None
    lat: float | None = None
    lon: float | None = None
    ele: float | None = None
    symbol: str | None = None
    notes: str | None = None


class PreferredUpdate(BaseModel):
    value: bool
    note: str | None = None


class VenueToPoiRequest(BaseModel):
    """Overrides when saving a venue onto the route; all optional."""

    name: str | None = None
    symbol: str | None = None
    notes: str | None = None


class DayUpdate(BaseModel):
    name: str | None = None
    order_index: int | None = None


class BoolValue(BaseModel):
    value: bool


class RotateRequest(BaseModel):
    index: int


class TrimRequest(BaseModel):
    start_index: int
    end_index: int


class SplitRequest(BaseModel):
    indices: list[int]


class MergeRequest(BaseModel):
    day_id_a: int
    day_id_b: int


class ReorderRequest(BaseModel):
    day_ids: list[int]
