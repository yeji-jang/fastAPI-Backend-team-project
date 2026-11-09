"""응용 계층: 공연 API의 작업 순서와 트랜잭션을 조율한다."""

from datetime import datetime, timezone

from asyncticket.shared.domain.catalog import (
    CatalogActor, CatalogConflictError, CatalogNotFoundError, CatalogPolicy,
    CatalogRelations, CatalogUnitOfWork,
)
from asyncticket.shows.domain.repositories import ShowRepository
from asyncticket.shows.domain.show import Show, ShowNotFoundError, ShowQuery


class ShowApplicationService:
    def __init__(
        self, repository: ShowRepository, relations: CatalogRelations,
        unit_of_work: CatalogUnitOfWork, policy: CatalogPolicy,
    ) -> None:
        # 인터페이스만 받으므로 SQLAlchemy나 FastAPI에 의존하지 않는다.
        self._repository = repository
        self._relations = relations
        self._uow = unit_of_work
        self._policy = policy

    async def find_by_id(self, show_id: int, *, for_update: bool = False) -> Show:
        show = await self._repository.find_by_id(show_id, for_update=for_update)
        if show is None:
            raise ShowNotFoundError("공연을 찾을 수 없습니다.")
        return show

    async def find_all(self, query: ShowQuery) -> tuple[list[Show], int]:
        return await self._repository.find_all(query)

    async def authorize_owner(self, show_id: int, actor: CatalogActor) -> Show:
        # 회차의 생성/수정/삭제도 같은 공연 행을 먼저 잠가 순서를 통일한다.
        self._policy.authorize(actor)
        show = await self.find_by_id(show_id, for_update=True)
        self._policy.authorize(actor, show.user_id)
        return show

    async def create(self, values: dict[str, object], actor: CatalogActor) -> Show:
        try:
            self._policy.authorize(actor)
            Show.validate_creation(values, self._policy)
            if not await self._relations.venue_exists(values["venues_id"]):
                raise CatalogNotFoundError("공연장을 찾을 수 없습니다.")
            # 소유자는 요청 본문이 아닌, 검증된 인증 사용자에서 정한다.
            show = await self._repository.create({**values, "user_id": actor.user_id})
            await self._uow.commit()
            return show
        except Exception:
            await self._uow.rollback()
            raise

    async def update(
        self, show_id: int, changes: dict[str, object], actor: CatalogActor,
    ) -> Show:
        try:
            show = await self.authorize_owner(show_id, actor)
            changed = show.with_changes(changes, self._policy)
            if "venues_id" in changes and changes["venues_id"] != show.venues_id:
                if not await self._relations.venue_exists(changes["venues_id"]):
                    raise CatalogNotFoundError("공연장을 찾을 수 없습니다.")
                if await self._relations.show_has_performances(show_id):
                    raise CatalogConflictError("회차가 연결된 공연의 공연장은 변경할 수 없습니다.")
            show = await self._repository.update(
                show_id, {
                    **{key: getattr(changed, key) for key in changes},
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            await self._uow.commit()
            return show
        except Exception:
            await self._uow.rollback()
            raise

    async def delete(self, show_id: int, actor: CatalogActor) -> None:
        try:
            await self.authorize_owner(show_id, actor)
            if await self._relations.show_has_performances(show_id):
                raise CatalogConflictError("회차가 연결된 공연은 삭제할 수 없습니다.")
            await self._repository.delete(show_id)
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
