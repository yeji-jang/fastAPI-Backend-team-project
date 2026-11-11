"""인프라 계층: 공연 조회·저장 SQL을 실행하고 결과를 도메인 객체로 변환한다."""

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.dml import Insert, Update

from asyncticket.shows.domain.show import Show, ShowQuery
from asyncticket.shows.infrastructure.models import ShowModel
from asyncticket.shared.domain.catalog import CatalogConflictError


class SqlAlchemyShowRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _to_domain(model: ShowModel) -> Show:
        return Show(
            show_id=model.show_id, venues_id=model.venues_id, user_id=model.user_id,
            title=model.title, description=model.description, performer=model.performer,
            type=model.type, runtime=model.runtime, created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def find_by_id(self, show_id: int, *, for_update: bool = False) -> Show | None:
        statement = select(ShowModel).where(ShowModel.show_id == show_id).execution_options(
            populate_existing=True
        )
        if for_update:
            statement = statement.with_for_update()
        model = await self._session.scalar(statement)
        return self._to_domain(model) if model is not None else None

    async def find_all(self, query: ShowQuery) -> tuple[list[Show], int]:
        conditions = []
        if query.keyword:
            # 검색어의 %와 _는 와일드카드가 아닌 제목의 실제 문자로 취급한다.
            conditions.append(ShowModel.title.icontains(query.keyword, autoescape=True))
        if query.type is not None:
            conditions.append(ShowModel.type == query.type)
        if query.venues_id is not None:
            conditions.append(ShowModel.venues_id == query.venues_id)
        total = await self._session.scalar(
            select(func.count()).select_from(ShowModel).where(*conditions)
        )
        models = await self._session.scalars(
            select(ShowModel).where(*conditions)
            .order_by(ShowModel.created_at.desc(), ShowModel.show_id.desc())
            .offset((query.page - 1) * query.size).limit(query.size)
        )
        return [self._to_domain(model) for model in models], int(total or 0)

    async def create(self, values: dict[str, object]) -> Show:
        return await self._write(insert(ShowModel.__table__).values(**values))

    async def update(self, show_id: int, values: dict[str, object]) -> Show:
        return await self._write(
            update(ShowModel.__table__).where(ShowModel.show_id == show_id).values(**values)
        )

    async def _write(self, statement: Insert | Update) -> Show:
        # SQL은 이 계층에서 실행하지만 commit은 응용 계층에 맡긴다.
        try:
            result = await self._session.execute(statement.returning(*ShowModel.__table__.c))
        except IntegrityError as exc:
            raise CatalogConflictError("공연과 연결된 데이터가 충돌합니다.") from exc
        return Show(**result.mappings().one())

    async def delete(self, show_id: int) -> None:
        try:
            await self._session.execute(
                delete(ShowModel.__table__).where(ShowModel.show_id == show_id)
            )
        except IntegrityError as exc:
            raise CatalogConflictError("연결된 데이터가 있어 공연을 삭제할 수 없습니다.") from exc
