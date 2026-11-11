"""도메인 계층: 공연 회차 데이터와 회차 없음 예외를 정의한다."""

from dataclasses import dataclass
from datetime import datetime

from asyncticket.shared.domain.catalog import CatalogNotFoundError


@dataclass(frozen=True)
class Performance:
    perf_id: int
    show_id: int
    round_number: int
    starts_at: datetime
    ends_at: datetime
    booking_opens_at: datetime
    booking_closes_at: datetime
    max_tickets_per_user: int
    status: str


class PerformanceNotFoundError(CatalogNotFoundError):
    pass
