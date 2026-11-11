"""도메인 계층의 저장소 인터페이스: 회차 조회·중복 검사·저장 계약을 정의한다."""

from datetime import datetime
from typing import Protocol

from asyncticket.performances.domain.performance import Performance


class PerformanceRepository(Protocol):
    async def find_by_id(self, perf_id: int, *, for_update: bool = False) -> Performance | None: ...

    async def find_all(
        self, show_id: int, starts_from: datetime | None, starts_until: datetime | None,
    ) -> list[Performance]: ...

    async def round_exists(
        self, show_id: int, round_number: int, exclude_id: int | None = None,
    ) -> bool: ...

    async def create(self, values: dict[str, object]) -> Performance: ...

    async def update(self, perf_id: int, values: dict[str, object]) -> Performance: ...

    async def delete(self, perf_id: int) -> None: ...
