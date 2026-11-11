from typing import Annotated, Any, Callable

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from asyncticket.venues.application.service import VenueService
from asyncticket.venues.domain.repository import VenueRepository
from asyncticket.venues.infrastructure.repositories import SqlAlchemyVenueRepository
from asyncticket.venues.presentation.dependencies import provider_venue_service


def wire_dependencies(
    app: FastAPI,
    db_dependency: Callable[..., Any] | None = None,
) -> None:
    if db_dependency is None:
        from asyncticket.shared.core.database import get_db

        db_dependency = get_db

    def create_venue_repository(
        session: Annotated[AsyncSession, Depends(db_dependency)],
    ) -> VenueRepository:
        return SqlAlchemyVenueRepository(session)

    def create_venue_service(
        repository: Annotated[VenueRepository, Depends(create_venue_repository)],
    ) -> VenueService:
        return VenueService(repository)

    app.dependency_overrides[provider_venue_service] = create_venue_service
