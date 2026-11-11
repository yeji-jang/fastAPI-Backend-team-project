"""도메인 계층: 입력 경로와 무관하게 지켜야 할 값·시간순서 규칙을 검사한다."""

from datetime import datetime
from typing import Mapping

from asyncticket.shared.domain.catalog import CatalogPolicy, CatalogValidationError


def validate_show(values: Mapping[str, object], policy: CatalogPolicy) -> None:
    for field, limit in (("title", 255), ("type", 50)):
        value = values[field]
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise CatalogValidationError(f"{field} 입력값을 확인해 주세요.")
    if policy.show_types is not None and values["type"] not in policy.show_types:
        raise CatalogValidationError("허용되지 않은 공연 분류입니다.")
    runtime = values["runtime"]
    if runtime is not None and (type(runtime) is not int or runtime <= 0):
        raise CatalogValidationError("공연 시간은 양수여야 합니다.")


def validate_performance(values: Mapping[str, object], policy: CatalogPolicy) -> None:
    times = [values[name] for name in (
        "booking_opens_at", "booking_closes_at", "starts_at", "ends_at"
    )]
    if any(not isinstance(value, datetime) or value.utcoffset() is None for value in times):
        raise CatalogValidationError("모든 시각에 시간대가 필요합니다.")
    opens, closes, starts, ends = times
    if not opens < closes <= starts < ends:
        raise CatalogValidationError("예매 시작 < 예매 마감 ≤ 공연 시작 < 공연 종료여야 합니다.")
    for field in ("round_number", "max_tickets_per_user"):
        value = values[field]
        if type(value) is not int or value <= 0:
            raise CatalogValidationError(f"{field} 값은 양수여야 합니다.")
    status = values["status"]
    if not isinstance(status, str) or not status.strip() or len(status) > 30:
        raise CatalogValidationError("회차 상태를 확인해 주세요.")
    if policy.performance_statuses is not None and status not in policy.performance_statuses:
        raise CatalogValidationError("허용되지 않은 회차 상태입니다.")
