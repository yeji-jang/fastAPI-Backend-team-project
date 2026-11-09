"""좌석 조회 실패를 팀 공통 오류 응답에 연결한다.

서비스는 실패 의미를 선택하고, HTTP 상태와 오류 식별자는 여기서 정한다.
좌석의 업무 상태는 domain.enums.SeatStatus에서 관리한다.
"""

from asyncticket.shared.core.exceptions import NotFoundException, SharedException

# 기존 호출자의 import 경로를 유지한다. 정의는 도메인에 둔다.
from asyncticket.seats.domain.seat_info import (
    SeatInfoNotFoundError as SeatInfoNotFoundError,
)


class PerformanceNotFoundError(NotFoundException):
    def __init__(self, message: str):
        super().__init__(message, error_code="PERFORMANCE_NOT_FOUND")


class SeatNotFoundError(NotFoundException):
    def __init__(self, message: str):
        super().__init__(message, error_code="SEAT_NOT_FOUND")


class ReservationSeatsNotFoundError(NotFoundException):
    def __init__(self, message: str):
        super().__init__(message, error_code="RESERVATION_NOT_FOUND")


class SeatLookupIntegrityError(SharedException):
    def __init__(self, message: str):
        super().__init__(
            message, status_code=500, error_code="SEAT_LOOKUP_INTEGRITY_ERROR"
        )


class ReservationSeatIntegrityError(SharedException):
    def __init__(self, message: str):
        super().__init__(
            message, status_code=500, error_code="RESERVATION_SEAT_INTEGRITY_ERROR"
        )
