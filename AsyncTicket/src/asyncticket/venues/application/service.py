from asyncticket.venues.domain.repository import VenueRepository
from asyncticket.venues.domain.venue import Venue
from asyncticket.shared.core.exceptions import (
    ConflictException,
    NotFoundException,
)


class VenueService:
    def __init__(self, repository: VenueRepository):
        self.repo = repository

    async def create_venue(
        self, name: str, address: str, address_detail: str, post_no: str
    ) -> Venue:
        if await self.repo.find_by_post_no(None, post_no):
            raise ConflictException(
                "이미 사용중인 공연장입니다.", error_code="VENUE_ALREADY_EXISTS"
            )

        venue = Venue.create(
            name=name, address=address, address_detail=address_detail, post_no=post_no
        )

        return await self.repo.save(venue)

    async def update_venue(
        self,
        venues_id: int,
        changes: dict,
    ) -> Venue:
        venue = await self.repo.find_by_id(venues_id)

        if venue is None:
            raise NotFoundException(
                "수정할 공연장이 없습니다.", error_code="VENUE_NOT_FOUND"
            )

        post_no = changes.get("post_no", venue.post_no)

        if post_no != venue.post_no:
            if await self.repo.find_by_post_no(venues_id, post_no):
                raise ConflictException(
                    "이미 사용중인 공연장입니다.", error_code="VENUE_ALREADY_EXISTS"
                )

        venue.update_info(
            name=changes.get("name", venue.name),
            address=changes.get("address", venue.address),
            address_detail=changes.get("address_detail", venue.address_detail),
            post_no=post_no,
        )

        return await self.repo.save(venue)

    async def get_venue(self, venues_id: int) -> Venue:
        venue = await self.repo.find_by_id(venues_id)

        if venue is None:
            raise NotFoundException(
                "공연장을 찾을 수 없습니다.",
                error_code="VENUE_NOT_FOUND",
            )

        return venue

    async def get_list_venue(
        self, name: str, address: str, page: int, page_size: int
    ) -> list[Venue]:
        return await self.repo.find_by_filters(name, address, page, page_size)
