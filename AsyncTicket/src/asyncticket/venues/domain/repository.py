from abc import ABC, abstractmethod
from asyncticket.venues.domain.venue import Venue


class VenueRepository(ABC):

    @abstractmethod
    async def find_by_id(self, venues_id: int) -> Venue | None:
        """venues_id로 공연장 단건 조회"""
        pass

    @abstractmethod
    async def find_by_post_no(self, venues_id: int, post_no: str) -> Venue | None:
        """현재 들어온 venues_id가 아닌 post_no로 공연장 중복 체크"""
        pass

    @abstractmethod
    async def find_by_filters(
        self, name: str, address: str, page: int, page_size: int
    ) -> list[Venue]:
        """이름과 주소 조건에 맞는 공연장 목록을 페이지 단위로 조회한다."""
        pass

    @abstractmethod
    async def save(self, venue: Venue) -> Venue:
        """공연장 신규 생성 및 수정"""
        pass
