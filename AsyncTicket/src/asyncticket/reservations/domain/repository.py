"""
예매 저장소 약속
    1) 예매를 저장 (예매생성은 reservation.py-Reservation에서)
    2) 예매 ID로 찾고
    3) 회원의 예매 목록을 찾고
    4) 바뀐 상태(취소, 확정, 만료)를 저장
    5) 만료 대상 예매대기 목록을 찾는다
"""

from abc import ABC, abstractmethod
from datetime import datetime
from asyncticket.reservations.domain.reservation import Reservation
from asyncticket.reservations.domain.enums import ReservationStatus


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
        reservation:Reservation,
        expected_status:ReservationStatus) -> bool :
        """4) DB 상태가 expected_status일 때만 바뀐 상태(확정, 취소, 만료)를 저장
              성공하면 True, 그 사이 다른 요청이 상태를 바꿨으면 False"""
        pass


    @abstractmethod
    async def find_pending_created_before(
        self,
        before : datetime) -> list[Reservation] :
        """5) before 이전에 생성된 예매대기(PENDING) 목록 찾기 (만료대상), 없으면 빈리스트[]"""
        pass