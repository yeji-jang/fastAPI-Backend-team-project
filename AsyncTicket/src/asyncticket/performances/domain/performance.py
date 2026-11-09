"""회차의 값·시간순서 검증과 정보 변경을 담당하는 순수 도메인 모델."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from typing import ClassVar, Self

from asyncticket.shared.domain.catalog import (
    CatalogNotFoundError, CatalogPolicy, CatalogValidationError,
)
from asyncticket.shared.domain.catalog_validation import validate_performance


@dataclass(frozen=True)
class Performance:
    _MUTABLE_FIELDS: ClassVar[frozenset[str]] = frozenset({
        "round_number", "starts_at", "ends_at", "booking_opens_at",
        "booking_closes_at", "max_tickets_per_user", "status",
    })

    perf_id: int
    show_id: int
    round_number: int
    starts_at: datetime
    ends_at: datetime
    booking_opens_at: datetime
    booking_closes_at: datetime
    max_tickets_per_user: int
    status: str

    def __post_init__(self) -> None:
        # 과거 회차도 같은 시간순서 규칙을 따른다. 현재 시각 제한은 추가하지 않는다.
        # 앱별 상태 허용값은 저장된 객체를 복원할 때 강제하지 않는다.
        validate_performance(asdict(self), CatalogPolicy())

    @staticmethod
    def validate_creation(values: Mapping[str, object], policy: CatalogPolicy) -> None:
        """DB가 ID를 발급하기 전에 등록할 회차 값을 검증한다."""
        validate_performance(values, policy)

    def with_changes(self, changes: Mapping[str, object], policy: CatalogPolicy) -> Self:
        """부분 변경을 기존 값과 합쳐 검증하고 새 회차를 반환한다."""
        if changes.keys() - self._MUTABLE_FIELDS:
            raise CatalogValidationError("회차의 변경할 수 없는 필드입니다.")
        self.validate_creation({**asdict(self), **changes}, policy)
        return replace(self, **changes)


class PerformanceNotFoundError(CatalogNotFoundError):
    pass
