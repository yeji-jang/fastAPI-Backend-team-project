from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from asyncticket.venues.domain.repository import VenueRepository
from asyncticket.venues.domain.venue import Venue
from asyncticket.venues.infrastructure.models import VenueModel


class SqlAlchemyVenueRepository(VenueRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def find_by_id(self, venues_id) -> Venue | None:
        stmt = select(VenueModel).where(VenueModel.venues_id == venues_id)
        venue_model = await self.session.scalar(stmt)
        return venue_model.to_venue() if venue_model else None

    async def find_by_post_no(
        self,
        venues_id: int | None,
        post_no: str,
    ) -> Venue | None:
        stmt = select(VenueModel).where(VenueModel.post_no == post_no)

        if venues_id is not None:
            stmt = stmt.where(VenueModel.venues_id != venues_id)

        venue_model = await self.session.scalar(stmt)
        return venue_model.to_venue() if venue_model is not None else None

    async def find_by_filters(self, name, address, page, page_size) -> list[Venue]:
        stmt = select(VenueModel)

        if name is not None:
            stmt = stmt.where(VenueModel.name.contains(name))

        if address is not None:
            stmt = stmt.where(
                func.concat(
                    VenueModel.address, func.coalesce(VenueModel.address_detail, "")
                ).contains(address)
            )

        stmt = (
            stmt.limit(page_size)
            .offset((page - 1) * page_size)
            .order_by(VenueModel.name)
        )

        result = await self.session.scalars(stmt)
        models = result.all()

        return [model.to_venue() for model in models]

    async def save(self, venue) -> Venue:
        # 신규 등록
        if venue.venues_id is None:
            venue_model = VenueModel(
                name=venue.name,
                address=venue.address,
                address_detail=venue.address_detail,
                post_no=venue.post_no,
            )

            self.session.add(venue_model)

        else:
            # 기존 수정
            stmt = select(VenueModel).where(VenueModel.venues_id == venue.venues_id)
            venue_model = await self.session.scalar(stmt)

            venue_model.name = venue.name
            venue_model.address = venue.address
            venue_model.address_detail = venue.address_detail
            venue_model.post_no = venue.post_no

        await self.session.commit()
        await self.session.refresh(venue_model)

        return venue_model.to_venue()
