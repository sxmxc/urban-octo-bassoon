from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlmodel import Session

from app.models import EndpointDefinition
from app.schemas import EndpointCreate, EndpointUpdate
from app.services.route_runtime import delete_route_runtime_records
from app.time_utils import utc_now


def get_endpoint(session: Session, endpoint_id: int) -> Optional[EndpointDefinition]:
    return session.get(EndpointDefinition, endpoint_id)


def get_endpoint_by_path(session: Session, path: str, method: str) -> Optional[EndpointDefinition]:
    statement = select(EndpointDefinition).where(
        EndpointDefinition.path == path,
        EndpointDefinition.method == method.upper(),
        EndpointDefinition.enabled == True,
    )
    return session.execute(statement).scalars().first()


def list_endpoints(session: Session, limit: int = 100, offset: int = 0) -> List[EndpointDefinition]:
    statement = select(EndpointDefinition).order_by(EndpointDefinition.id).offset(offset).limit(limit)
    return list(session.execute(statement).scalars())


def create_endpoint(session: Session, endpoint_in: EndpointCreate) -> EndpointDefinition:
    endpoint = EndpointDefinition(**endpoint_in.model_dump())
    session.add(endpoint)
    session.commit()
    session.refresh(endpoint)
    return endpoint


def update_endpoint(session: Session, endpoint: EndpointDefinition, endpoint_in: EndpointUpdate) -> EndpointDefinition:
    data = endpoint_in.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(endpoint, key, value)
    endpoint.updated_at = utc_now()
    session.add(endpoint)
    session.commit()
    session.refresh(endpoint)
    return endpoint


def delete_endpoint(session: Session, endpoint: EndpointDefinition, *, commit: bool = True) -> None:
    delete_route_runtime_records(session, int(endpoint.id or 0))
    session.delete(endpoint)
    if commit:
        session.commit()
