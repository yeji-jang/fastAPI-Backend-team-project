"""회차 응용 서비스가 공연 기능에 요구하는 계약."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from asyncticket.shared.domain.catalog import CatalogActor


@dataclass(frozen=True)
class ShowReference:
    """회차 기능이 참조하는 공연의 최소 정보."""

    show_id: int


class ShowAccess(ABC):
    @abstractmethod
    async def find_by_id(
        self, show_id: int, *, for_update: bool = False,
    ) -> ShowReference:
        """공연을 확인한다. 없으면 기존 공연 예외를 전달한다."""
        raise NotImplementedError

    @abstractmethod
    async def authorize_owner(
        self, show_id: int, actor: CatalogActor,
    ) -> ShowReference:
        """같은 요청 세션에서 공연을 잠그고 소유권을 확인한다.

        반환 전에 commit하지 않으며 잠금은 회차 변경의
        commit/rollback까지 유지한다.
        """
        raise NotImplementedError
