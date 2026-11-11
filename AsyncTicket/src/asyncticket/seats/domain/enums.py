# <좌석 상태·등급 약속>
# - 상태 이름은 정의하되 선점·확정·해제의 전이 시점은 호출부와 맞춘다.

# seats/domain/enums.py
from enum import StrEnum


class SeatStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    OCCUPIED = "OCCUPIED"


class SeatGrade(StrEnum):
    R = "R석"
    S = "S석"


class SeatReservationAction(StrEnum):
    """연결·해제 요청의 종류. 좌석 상태값과는 구분한다."""

    ASSIGN = "연결"
    RELEASE = "해제"
