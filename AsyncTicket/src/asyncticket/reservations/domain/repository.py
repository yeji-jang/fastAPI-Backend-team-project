"""
예매 저장소 약속
    1) 예매를 저장 (예매생성은 reservation.py-Reservation에서)
    2) 예매 ID로 찾고
    3) 회원의 예매 목록을 찾고
    4) 바뀐 상태(취소, 확정)를 저장
"""

from abc import ABC, abstractmethod
from asyncticket.reservations.domain.reservation import Reservation


class ReservationRepository(ABC):

    @abstractmethod
    async def reserv_add(
        self, 
        reservation:Reservation) -> Reservation:
        """1) 예매 저장후 reserv_id가 채워진 예매를 돌려준다"""
        pass

    @abstractmethod
    async def find_by_reserv_id(
        self, 
        reserv_id : int) -> Reservation | None :
        """2) 예매 ID 찾기 없으면 None 반환"""
        pass

    @abstractmethod
    async def find_all_by_ticketholder(
        self, 
        ticketholder_id: int) -> list[Reservation] :
        """3) 회원의 예매 목록을 찾기 없으면 빈리스트[]를 반환"""
        pass

    @abstractmethod
    async def reserv_status_update(
        self,
        reservation:Reservation) -> None :
        """4) 예매 상태 변경(확정,취소)을 저장"""
        pass
