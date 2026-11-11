"""도메인 계층: 공연·회차에서 함께 사용하는 사용자·정책·연결 조회·트랜잭션 계약."""

from dataclasses import dataclass
from typing import Protocol


class CatalogValidationError(ValueError):
    pass


class CatalogNotFoundError(LookupError):
    pass


class CatalogForbiddenError(PermissionError):
    pass


class CatalogConflictError(Exception):
    pass


class AuthenticationRequiredError(Exception):
    pass


class CatalogIntegrationError(Exception):
    pass


@dataclass(frozen=True)
class CatalogActor:
    user_id: int
    role: str


@dataclass(frozen=True)
class CatalogPolicy:
    """명세에서 아직 제안인 정책의 구현 선택을 한곳에서 관리한다."""

    admin_can_manage_all: bool = True
    show_types: frozenset[str] | None = None
    performance_statuses: frozenset[str] | None = None
    # 연결 회차의 일정·회차번호·매수 변경 제한이다. 상태만 바꾸는 요청은 허용한다.
    block_performance_changes_with_links: bool = True

    def authorize(self, actor: CatalogActor, owner_id: int | None = None) -> None:
        if actor.role == "ADMIN" and self.admin_can_manage_all:
            return
        if actor.role == "SELLER" and (owner_id is None or actor.user_id == owner_id):
            return
        raise CatalogForbiddenError("공연을 변경할 권한이 없습니다.")


class CatalogAuthenticator(Protocol):
    async def authenticate(self, token: str) -> CatalogActor | None: ...


class CatalogUnitOfWork(Protocol):
    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class CatalogRelations(Protocol):
    async def venue_exists(self, venues_id: int) -> bool: ...

    async def show_has_performances(self, show_id: int) -> bool: ...

    async def performance_has_seats(self, perf_id: int) -> bool: ...

    async def performance_has_reservations(self, perf_id: int) -> bool: ...
