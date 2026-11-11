from asyncticket.venues.application.service import VenueService
from asyncticket.venues.domain.repository import VenueRepository


def provider_venue_service() -> VenueService:
    raise NotImplementedError("VenueService 의존성이 주입되지 않았습니다.")


def provider_venue_repository() -> VenueRepository:
    raise NotImplementedError("VenueRepository 의존성이 주입되지 않았습니다.")
