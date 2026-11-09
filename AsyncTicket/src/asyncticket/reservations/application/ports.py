"""
응용 계층이 다른 도메인에 요청하는 기능 (포트)
    - 예매 application은 좌석 코드를 직접 알지 않고 이 약속만 사용
    - 좌석을 잡거나 / 놓거나라는 의도만 전달 
    - 좌석 상태 값은 모름
    - 실제 구현(좌석 상태 값 채우기)은 infrastructure의 어댑터가 함
      → 좌석 상태가 바뀌어도 어댑터만 고치면 된다
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