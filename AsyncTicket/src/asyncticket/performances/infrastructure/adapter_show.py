"""회차의 공연 접근 계약을 기존 공연 서비스에 연결한다."""

from asyncticket.performances.application.ports import ShowAccess, ShowReference
from asyncticket.shared.domain.catalog import CatalogActor
from asyncticket.shows.application.service import ShowApplicationService


class ShowServiceAdapter(ShowAccess):
    def __init__(self, service: ShowApplicationService) -> None:
        self._service = service

    async def find_by_id(
        self, show_id: int, *, for_update: bool = False,
    ) -> ShowReference:
        show = await self._service.find_by_id(show_id, for_update=for_update)
        return ShowReference(show_id=show.show_id)

    async def authorize_owner(
        self, show_id: int, actor: CatalogActor,
    ) -> ShowReference:
        show = await self._service.authorize_owner(show_id, actor)
        return ShowReference(show_id=show.show_id)
