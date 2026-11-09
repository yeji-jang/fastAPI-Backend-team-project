"""
외부 데이터 조회 인터페이스 (추상화)

<기준 1> 외부 데이터(DB)를 참고해야 하는 것
    - ReservationChecker        : 회원 1명은 회차 1개에 확정 예매 1건 (다른 예매 조회)
    - ReservedPerformanceReader : 예매 기간·공연 시작 일시 (회차 조회 → VO)
    - ReservedSeatReader        : 좌석 가격 (좌석 조회 → VO)

<기준 2> 다른 도메인이 써야 하는 예매 데이터
    - ReservationStatusReader   : 예매 상태 (결제·좌석·회차 도메인이 사용)

※ 판단은 예매(reservation.py)가 한다. 여기서는 값을 가져오는 약속만 둔다.
"""

from abc import ABC, abstractmethod

from asyncticket.reservations.domain.enums import ReservationStatus
from asyncticket.reservations.domain.reservation import ReservedPerformance, ReservedSeat, ReservedPayment


# ---------- 기준 1 : 외부 데이터 참고 ----------
class ReservationChecker(ABC):
    """이 회원이 이 회차에 예매할 수 있는지 확인 -> 확정된 예매가 없으면 가능"""
    @abstractmethod
    async def is_reserv_possible(
        self,
        ticketholder_id: int,
        perf_id: int
        ) -> bool:
        pass

class ReservedPerformanceReader(ABC): 
    """회차 정보(예매기간, 공연시작)를 예매 VO로 가져온다 없으면 None"""
    @abstractmethod
    async def get_reserved_performance(
        self,
        perf_id: int
    ) -> ReservedPerformance | None :
        pass

class ReservedSeatReader(ABC):
    """좌석 정보(좌석, 가격)를 예매 VO로 가져온다. 해당 회차의 좌석이 아니면 None"""
    @abstractmethod
    async def get_reserved_seat(
        self,
        perf_id: int,
        perf_seat_id: int,
    ) -> ReservedSeat | None : 
        pass

# ---------- 기준 2 : 다른 도메인에 예매 데이터 제공 ----------
class ReservationStatusReader(ABC):
    """예매상태를 알려준다 (예매 확정 / 취소) | 예매가 없으면 None"""
    @abstractmethod
    async def get_reserved_status(
        self,
        reserv_id : int
    ) -> ReservationStatus | None :
        pass