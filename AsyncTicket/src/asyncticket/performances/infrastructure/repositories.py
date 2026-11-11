"""인프라 계층: 회차 SQL을 실행한다. 트랜잭션 확정은 응용 계층에 맡긴다."""

from datetime import datetime

from sqlalchemy import delete, exists, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.dml import Insert, Update

from asyncticket.performances.domain.performance import Performance
from asyncticket.performances.infrastructure.models import PerformanceModel
from asyncticket.shared.domain.catalog import CatalogConflictError


class SqlAlchemyPerformanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _to_domain(model: PerformanceModel) -> Performance:
        return Performance(
            perf_id=model.perf_id, show_id=model.show_id, round_number=model.round_number,
            starts_at=model.starts_at, ends_at=model.ends_at,
            booking_opens_at=model.booking_opens_at, booking_closes_at=model.booking_closes_at,
            max_tickets_per_user=model.max_tickets_per_user, status=model.status,
        )

    async def find_by_id(self, perf_id: int, *, for_update: bool = False) -> Performance | None:
        statement = select(PerformanceModel).where(
            PerformanceModel.perf_id == perf_id
        ).execution_options(populate_existing=True)
        if for_update:
            statement = statement.with_for_update()
        model = await self._session.scalar(statement)
        return self._to_domain(model) if model is not None else None

    async def find_all(
        self, show_id: int, starts_from: datetime | None, starts_until: datetime | None,
    ) -> list[Performance]:
        statement = select(PerformanceModel).where(PerformanceModel.show_id == show_id)
        if starts_from is not None:
            statement = statement.where(PerformanceModel.starts_at >= starts_from)
        if starts_until is not None:
            statement = statement.where(PerformanceModel.starts_at < starts_until)
        models = await self._session.scalars(
            statement.order_by(PerformanceModel.starts_at, PerformanceModel.perf_id)
        )
        return [self._to_domain(model) for model in models]

    async def round_exists(
        self, show_id: int, round_number: int, exclude_id: int | None = None,
    ) -> bool:
        conditions = [
            PerformanceModel.show_id == show_id,
            PerformanceModel.round_number == round_number,
        ]
        if exclude_id is not None:
            conditions.append(PerformanceModel.perf_id != exclude_id)
        return bool(await self._session.scalar(select(exists().where(*conditions))))

    async def create(self, values: dict[str, object]) -> Performance:
        return await self._write(insert(PerformanceModel.__table__).values(**values))

    async def update(self, perf_id: int, values: dict[str, object]) -> Performance:
        return await self._write(
            update(PerformanceModel.__table__).where(PerformanceModel.perf_id == perf_id)
            .values(**values)
        )

    async def _write(self, statement: Insert | Update) -> Performance:
        try:
            result = await self._session.execute(
                statement.returning(*PerformanceModel.__table__.c)
            )
        except IntegrityError as exc:
            raise CatalogConflictError("공연 회차와 연결된 데이터가 충돌합니다.") from exc
        return Performance(**result.mappings().one())

    async def delete(self, perf_id: int) -> None:
        try:
            await self._session.execute(
                delete(PerformanceModel.__table__).where(PerformanceModel.perf_id == perf_id)
            )
        except IntegrityError as exc:
            raise CatalogConflictError("연결된 데이터가 있어 회차를 삭제할 수 없습니다.") from exc
