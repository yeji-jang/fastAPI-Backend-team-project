"""응용 계층: 공연 소유권, 회차 규칙, 연결 데이터와 트랜잭션을 조율한다."""

from dataclasses import asdict
from datetime import date, datetime, time, timedelta, timezone

from asyncticket.performances.application.ports import ShowAccess
from asyncticket.performances.domain.performance import Performance, PerformanceNotFoundError
from asyncticket.performances.domain.repositories import PerformanceRepository
from asyncticket.shared.domain.catalog import (
    CatalogActor, CatalogConflictError, CatalogPolicy, CatalogRelations, CatalogUnitOfWork,
    CatalogValidationError,
)
from asyncticket.shared.domain.catalog_validation import validate_performance

KST = timezone(timedelta(hours=9), name="Asia/Seoul")
# KST 자정의 UTC 변환과 다음 날짜 경계 조회에 안전한 범위를 함께 사용한다.
PERFORMANCE_DATE_MIN = date.min + timedelta(days=1)
PERFORMANCE_DATE_MAX = date.max - timedelta(days=1)


class PerformanceApplicationService:
    def __init__(
        self, repository: PerformanceRepository, show_service: ShowAccess,
        relations: CatalogRelations, unit_of_work: CatalogUnitOfWork, policy: CatalogPolicy,
    ) -> None:
        self._repository = repository
        self._show_service = show_service
        self._relations = relations
        self._uow = unit_of_work
        self._policy = policy

    async def find_by_id(self, perf_id: int, *, for_update: bool = False) -> Performance:
        performance = await self._repository.find_by_id(perf_id, for_update=for_update)
        if performance is None:
            raise PerformanceNotFoundError("공연 회차를 찾을 수 없습니다.")
        return performance

    async def ensure_show_exists(self, show_id: int) -> None:
        """공개 회차 목록의 캐시 hit에서도 부모 공연의 존재를 확인한다."""
        await self._show_service.find_by_id(show_id)

    async def find_all(self, show_id: int, on_date: date | None) -> list[Performance]:
        await self.ensure_show_exists(show_id)
        starts_from = starts_until = None
        if on_date is not None:
            # 라우터 외의 호출도 Python datetime 범위를 벗어나지 않게 검사한다.
            if not PERFORMANCE_DATE_MIN <= on_date <= PERFORMANCE_DATE_MAX:
                raise CatalogValidationError("조회 날짜는 0001-01-02부터 9999-12-30까지 가능합니다.")
            # 한국 날짜의 자정 이상~다음 자정 미만을 UTC 조회 범위로 바꾼다.
            starts_from = datetime.combine(on_date, time.min, tzinfo=KST).astimezone(timezone.utc)
            starts_until = starts_from + timedelta(days=1)
        return await self._repository.find_all(show_id, starts_from, starts_until)

    async def create(
        self, show_id: int, values: dict[str, object], actor: CatalogActor,
    ) -> Performance:
        try:
            # 같은 공연의 회차 변경을 직렬화한 뒤 회차 번호 중복을 검사한다.
            await self._show_service.authorize_owner(show_id, actor)
            validate_performance(values, self._policy)
            if await self._repository.round_exists(show_id, values["round_number"]):
                raise CatalogConflictError("공연 안에서 회차 번호가 중복됩니다.")
            performance = await self._repository.create({**values, "show_id": show_id})
            await self._uow.commit()
            return performance
        except Exception:
            await self._uow.rollback()
            raise

    async def _authorize(self, perf_id: int, actor: CatalogActor) -> Performance:
        self._policy.authorize(actor)
        current = await self.find_by_id(perf_id)
        await self._show_service.authorize_owner(current.show_id, actor)
        return await self.find_by_id(perf_id, for_update=True)

    async def _has_links(self, perf_id: int) -> bool:
        return (
            await self._relations.performance_has_seats(perf_id)
            or await self._relations.performance_has_reservations(perf_id)
        )

    async def update(
        self, perf_id: int, changes: dict[str, object], actor: CatalogActor,
    ) -> Performance:
        try:
            performance = await self._authorize(perf_id, actor)
            before = asdict(performance)
            merged = {**before, **changes}
            # PATCH 입력 일부만 보지 않고, 기존 값과 합친 전체 시간순서를 검사한다.
            validate_performance(merged, self._policy)
            if await self._repository.round_exists(
                performance.show_id, merged["round_number"], exclude_id=perf_id,
            ):
                raise CatalogConflictError("공연 안에서 회차 번호가 중복됩니다.")
            changed_fields = {key for key, value in changes.items() if before[key] != value}
            # 좌석 생성 뒤에도 판매 상태는 바꿀 수 있다. 일정·회차번호·매수의
            # 실제 변경은 기존 연결 제한을 적용하며, 혼합 PATCH도 전체를 거절한다.
            if changed_fields - {"status"} and self._policy.block_performance_changes_with_links:
                if await self._has_links(perf_id):
                    raise CatalogConflictError("좌석 구성 또는 예매가 연결된 회차는 상태 외 정보를 변경할 수 없습니다.")
            performance = await self._repository.update(perf_id, changes)
            await self._uow.commit()
            return performance
        except Exception:
            await self._uow.rollback()
            raise

    async def delete(self, perf_id: int, actor: CatalogActor) -> None:
        try:
            await self._authorize(perf_id, actor)
            if await self._has_links(perf_id):
                raise CatalogConflictError("좌석 구성 또는 예매가 연결된 회차는 삭제할 수 없습니다.")
            # 연결 데이터의 취소·환불·연쇄 삭제는 이 API가 수행하지 않는다.
            await self._repository.delete(perf_id)
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
