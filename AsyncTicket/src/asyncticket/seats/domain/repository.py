# <도메인 - 좌석 저장소 약속>
# - 등급 저장소와 개별 좌석 저장소의 조회·저장 계약을 나눈다.

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TypedDict

from asyncticket.seats.domain.performance_seat import PerformanceSeat
from asyncticket.seats.domain.seat_info import SeatInfo


class SeatManagementContext(TypedDict):
    owner_id: int
    booking_opens_at: datetime


class SeatLookupConflictError(Exception):
    pass


class SeatInfoRepository(ABC):
    # 1) 등급 ID로 도메인 조회, 없으면 None
    @abstractmethod
    async def get_seat_info(self, seat_id: int) -> SeatInfo | None:
        pass

    # 2) 회차·등급 ID로 조회용 데이터 반환
    @abstractmethod
    async def get_seat_info_view(
        self, perf_id: int, seat_id: int
    ) -> dict[str, object] | None:
        pass

    # 3) 등급 저장
    @abstractmethod
    async def save_seat_info(self, seat_info: SeatInfo) -> SeatInfo:
        pass

    # 4) 같은 회차의 등급 중복 검사
    @abstractmethod
    async def grade_exists(self, perf_id: int, name: str) -> bool:
        pass

    # 5) 회차 잠금으로 좌석 구성 변경 직렬화
    @abstractmethod
    async def lock_performance(self, perf_id: int) -> bool:
        pass

    # 6) 회차 존재 여부 확인
    @abstractmethod
    async def performance_exists(self, perf_id: int) -> bool:
        pass

    # 7) 소유자·판매 시각을 관리 권한 검사에 제공
    @abstractmethod
    async def get_management_context(
        self, perf_id: int
    ) -> SeatManagementContext | None:
        pass

    # 8) 좌석 구성·가격 변경 트랜잭션 확정
    @abstractmethod
    async def commit(self) -> None:
        pass

    # 9) 좌석 구성·가격 변경 실패 시 취소
    @abstractmethod
    async def rollback(self) -> None:
        pass


class PerformanceSeatRepository(ABC):
    # 1) 개별 좌석 여러 건 저장
    @abstractmethod
    async def save_many(self, seats: list[PerformanceSeat]) -> None:
        """ID가 발급되지 않은 신규 좌석만 저장한다. 기존 좌석 수정은 지원하지 않는다."""
        pass

    # 2) 같은 회차의 기존 좌석명 중복 검사
    @abstractmethod
    async def names_exist(self, perf_id: int, seat_seqs: list[str]) -> bool:
        pass

    # 3) 회차의 좌석 목록 조회
    @abstractmethod
    async def list_performance_seats(self, perf_id: int) -> list[dict[str, object]]:
        pass

    # 4) 회차·좌석명으로 상세 조회
    @abstractmethod
    async def get_performance_seat(
        self, perf_id: int, seat_seq: str
    ) -> dict[str, object] | None:
        pass

    # 5) 회원이 소유한 예매의 좌석 조회
    @abstractmethod
    async def get_owned_reservation_seats(
        self,
        reserv_id: int,
        user_id: int,
    ) -> dict[str, object] | None:
        pass

    # 예매 연결 성공은 True, 조건 불일치는 False로 반환한다.
    # 6) 조건이 맞는 미연결 좌석에 예매 연결
    @abstractmethod
    async def assign_reservation(
        self,
        *,
        perf_id: int,
        perf_seat_id: int,
        reserv_id: int,
        expected_status: str,
        reserved_status: str,
    ) -> bool:
        pass

    # 7) 회차·개별 좌석 ID로 예매용 조회
    @abstractmethod
    async def get_performance_seat_by_id(
        self,
        perf_id: int,
        perf_seat_id: int,
    ) -> dict[str, object] | None:
        """예매 연결에 쓰는 개별 좌석 ID로 회차·가격·현재 상태를 조회한다."""
        pass

    # 8) 현재 예매 연결이 일치하는 좌석만 해제
    @abstractmethod
    async def release_reservation(
        self,
        *,
        perf_id: int,
        perf_seat_id: int,
        reserv_id: int,
        expected_status: str,
        released_status: str,
    ) -> bool:
        """현재 예매 연결과 상태가 일치할 때만 해제한다. 트랜잭션은 호출자가 맡는다."""
        pass
