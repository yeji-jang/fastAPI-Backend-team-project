"""
응용 계층이 다른 도메인에 요청하는 기능 (포트)
    - 예매 application은 좌석&결제 코드를 직접 알지 않고 이 약속만 사용
    - 실제 구현은 infrastructure의 어댑터가 함
      → 좌석&결제 쪽이 바뀌어도 어댑터만 고치면 된다

    1) SeatAllocation
        - 좌석을 잡거나 / 놓거나라는 의도만 전달 
        - 좌석 상태 값은 모름
    2) PaymentRefund
        - 예매 취소 시 결제를 환불해 달라는 의도만 전달
        - 결제 상태 값은 모름
"""

from typing import Protocol

class SeatAllocation(Protocol) : 
    """
    - 좌석 배정 : 예매에 좌석을 잡거나(hold) 놓는다(release)
    """

    # 좌석 연결
    async def hold(
        self,
        *,
        perf_id : int,
        perf_seat_id : int,
        reserv_id : int,
        # expected_status : str,
        # reserved_status : str       # ← 연결 : reserved (예매됨)
    ) -> None : ... # 모양만 있고 구현은 없다

    # 좌석 해제
    async def release(
        self, 
        *,
        perf_id : int,
        perf_seat_id : int,
        reserv_id : int, 
        # expected_status : str,
        # released_status : str       # ← 해제 : released (풀림)
    ) -> None : ...


class PaymentRefund(Protocol) :
    """
    - 결제 환불 : 예매 취소 시 그 예매의 결제를 환불한다
    """

    # 환불 (실패하면 예외 -> 예매 취소까지 전체 rollback)
    async def refund(
        self,
        *,
        reserv_id : int,
        reason : str    # 취소 사유
    ) -> None  : ...