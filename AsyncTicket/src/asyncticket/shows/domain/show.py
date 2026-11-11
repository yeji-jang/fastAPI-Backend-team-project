"""도메인 계층: 공연 데이터를 표현한다. HTTP·SQLAlchemy 객체를 포함하지 않는다."""

from dataclasses import dataclass
from datetime import datetime

from asyncticket.shared.domain.catalog import CatalogNotFoundError


@dataclass(frozen=True)
class Show:
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


@dataclass(frozen=True)
class ShowQuery:
    page: int = 1
    size: int = 20
    keyword: str | None = None
    type: str | None = None
    venues_id: int | None = None


class ShowNotFoundError(CatalogNotFoundError):
    pass
