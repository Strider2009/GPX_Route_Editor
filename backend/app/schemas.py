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
