"""
좌석 배정 어댑터 (application/ports.py의 SeatAllocation 구현)
    - 예매 application의 "좌석 잡기 / 놓기" 요청을 좌석 서비스 호출로 바꿔 준다
    - 좌석 상태 값은 좌석 팀의 SeatStatus enum을 그대로 사용
    - 좌석 상태 규칙이 바뀌면 이 파일만 고친다
        - 잡기(hold)    : AVAILABLE → RESERVED (예매대기 중 선점)
        - 놓기(release) : RESERVED → AVAILABLE (예매 취소·결제 실패)
"""

# <Application - 예매>
from asyncticket.reservations.application.ports import SeatAllocation

# <좌석 도메인>
from asyncticket.seats.application.service import PerformanceSeatService
from asyncticket.seats.domain.enums import SeatStatus


class SeatAllocationAdapter(SeatAllocation):

    def __init__(self, seat_service: PerformanceSeatService):
        self.seat_service = seat_service

    # 좌석 잡기 : 예매에 연결
    async def hold(self, *, perf_id: int, perf_seat_id: int, reserv_id: int) -> None:
        await self.seat_service.assign_reservation(
            perf_id=perf_id,
            perf_seat_id=perf_seat_id,
            reserv_id=reserv_id,
            expected_status=SeatStatus.AVAILABLE,   # 지금 판매 가능해야 하고
            reserved_status=SeatStatus.RESERVED,    # 연결되면 예매됨
        )

    # 좌석 놓기 : 예매 연결 해제
    async def release(self, *, perf_id: int, perf_seat_id: int, reserv_id: int) -> None:
        await self.seat_service.release_reservation(
            perf_id=perf_id,
            perf_seat_id=perf_seat_id,
            reserv_id=reserv_id,
            expected_status=SeatStatus.RESERVED,    # 지금 예매됨이어야 하고
            released_status=SeatStatus.AVAILABLE,   # 해제되면 판매 가능
        )
