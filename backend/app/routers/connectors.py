from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import history
from ..database import get_db
from ..models import Connector, Day
from ..schemas import ConnectorCreate, ConnectorUpdate
from ..serializers import connector_schema, day_detail

router = APIRouter(tags=["connectors"])

VALID_TYPES = {"start_access", "end_access", "spur"}


def get_day_or_404(db: Session, day_id: int) -> Day:
    day = db.get(Day, day_id)
    if not day:
        raise HTTPException(404, "Day not found")
    return day


def get_connector_or_404(db: Session, connector_id: int) -> Connector:
    connector = db.get(Connector, connector_id)
    if not connector:
        raise HTTPException(404, "Connector not found")
    return connector


@router.post("/days/{day_id}/connectors")
def add_connector(day_id: int, payload: ConnectorCreate, db: Session = Depends(get_db)):
    day = get_day_or_404(db, day_id)
    if payload.type not in VALID_TYPES:
        raise HTTPException(400, f"type must be one of {sorted(VALID_TYPES)}")
    history.record(db, day.project_id, "Add connector")
    connector = Connector(
        day_id=day.id,
        name=payload.name,
        type=payload.type,
        points=[p.model_dump() for p in payload.points],
    )
    db.add(connector)
    db.commit()
    db.refresh(day)
    return day_detail(day)


@router.put("/connectors/{connector_id}")
def update_connector(connector_id: int, payload: ConnectorUpdate, db: Session = Depends(get_db)):
    connector = get_connector_or_404(db, connector_id)
    history.record(db, connector.day.project_id, "Edit connector")
    if payload.name is not None:
        connector.name = payload.name
    if payload.points is not None:
        connector.points = [p.model_dump() for p in payload.points]
    db.commit()
    db.refresh(connector)
    return connector_schema(connector)


@router.delete("/connectors/{connector_id}", status_code=204)
def delete_connector(connector_id: int, db: Session = Depends(get_db)):
    connector = get_connector_or_404(db, connector_id)
    history.record(db, connector.day.project_id, "Delete connector")
    db.delete(connector)
    db.commit()
