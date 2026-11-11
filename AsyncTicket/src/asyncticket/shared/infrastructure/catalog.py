"""인프라 계층: 외부 도메인 연결 조회와 DB 트랜잭션 인터페이스를 구현한다."""

from sqlalchemy import column, exists, select, table
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from asyncticket.shared.domain.catalog import CatalogConflictError

# 외부 도메인 컬럼의 조회 계약만 선언한다. 대체 ORM 모델을 등록하거나
# 공연장·좌석·예매 테이블을 생성하지 않는다.
venues = table("venues", column("venues_id"))
performances = table("performances", column("perf_id"), column("show_id"))
seats_info = table("seats_info", column("perf_id"))
reservations = table("reservations", column("perf_id"))


class SqlAlchemyCatalogRelations:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def venue_exists(self, venues_id: int) -> bool:
        return bool(await self._session.scalar(select(exists().where(
            venues.c.venues_id == venues_id
        ))))

    async def show_has_performances(self, show_id: int) -> bool:
        return bool(await self._session.scalar(select(exists().where(
            performances.c.show_id == show_id
        ))))

    async def performance_has_seats(self, perf_id: int) -> bool:
        return bool(await self._session.scalar(select(exists().where(
            seats_info.c.perf_id == perf_id
        ))))

    async def performance_has_reservations(self, perf_id: int) -> bool:
        return bool(await self._session.scalar(select(exists().where(
            reservations.c.perf_id == perf_id
        ))))


class SqlAlchemyCatalogUnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def commit(self) -> None:
        try:
            await self._session.commit()
        except IntegrityError as exc:
            raise CatalogConflictError("연결된 데이터와 충돌해 변경할 수 없습니다.") from exc

    async def rollback(self) -> None:
        await self._session.rollback()
