"""공연의 값 검증과 정보 변경을 담당하는 순수 도메인 모델."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from typing import ClassVar, Self

from asyncticket.shared.domain.catalog import (
    CatalogNotFoundError, CatalogPolicy, CatalogValidationError,
)
from asyncticket.shared.domain.catalog_validation import validate_show


@dataclass(frozen=True)
class Show:
    _MUTABLE_FIELDS: ClassVar[frozenset[str]] = frozenset({
        "venues_id", "title", "description", "performer", "type", "runtime",
    })

    show_id: int
    venues_id: int
    user_id: int
    title: str
    description: str | None
    performer: str | None
    type: str
    runtime: int | None
    created_at: datetime
    updated_at: datetime | None

    def __post_init__(self) -> None:
        # 저장된 데이터의 복원에도 값 자체의 규칙을 적용한다.
        # 앱별 분류 허용값은 쓰기 작업에서 전달받은 정책으로만 검사한다.
        validate_show(asdict(self), CatalogPolicy())

    @staticmethod
    def validate_creation(values: Mapping[str, object], policy: CatalogPolicy) -> None:
        """DB가 ID를 발급하기 전에 등록할 공연 값을 검증한다."""
        validate_show(values, policy)

    def with_changes(self, changes: Mapping[str, object], policy: CatalogPolicy) -> Self:
        """같은 show_id를 유지하는 변경 후보를 검증해 반환한다.

        생략한 값은 유지한다. 이 메서드는 DB에 행을 추가하거나 저장하지
        않는다. 응용 서비스가 공연장·회차 연결을 확인한 뒤 기존 행을 수정한다.
        """
        if changes.keys() - self._MUTABLE_FIELDS:
            raise CatalogValidationError("공연의 변경할 수 없는 필드입니다.")
        # 현재 정책의 검사 순서를 유지한 뒤 새 객체를 만든다.
        self.validate_creation({**asdict(self), **changes}, policy)
        return replace(self, **changes)


@dataclass(frozen=True)
class ShowQuery:
    page: int = 1
    size: int = 20
    keyword: str | None = None
    type: str | None = None
    venues_id: int | None = None


class ShowNotFoundError(CatalogNotFoundError):
    pass
