# <도메인 - 개별 좌석 규칙>
# - 개별 좌석의 ID·이름·상태·예매 참조 값만 검사한다. 결제·예매 상태는 판단하지 않는다.

# 1 예매 전용 좌석 도메인 (PerformanceSeat)
from asyncticket.seats.domain.enums import SeatStatus, SeatReservationAction
from dataclasses import dataclass
from asyncticket.shared.core.exceptions import ConflictException, ValidationException


@dataclass(frozen=True, kw_only=True)
class PerformanceSeat:
    """좌석 등급에 속한 개별 좌석. 예매 연결 전 reserv_id는 None이다."""

    seat_id: int
    seat_seq: str
    status: SeatStatus
    perf_seat_id: int | None = None
    reserv_id: int | None = None

    # 1) 개별 좌석을 만들 때 값 검사
    def __post_init__(self) -> None:
        if self.perf_seat_id is not None and (
            type(self.perf_seat_id) is not int or self.perf_seat_id <= 0
        ):
            raise ValidationException("개별 좌석 ID는 1 이상이어야 합니다.")

        if type(self.seat_id) is not int or self.seat_id <= 0:
            raise ValidationException("좌석 등급 ID는 1 이상이어야 합니다.")

        self.validate_seat_seq(self.seat_seq)

        if not isinstance(self.status, SeatStatus):
            raise ValidationException("좌석 상태는 SeatStatus 타입이어야 합니다.")

        if self.reserv_id is not None and (
            type(self.reserv_id) is not int or self.reserv_id <= 0
        ):
            raise ValidationException("예매 ID는 1 이상이어야 합니다.")

    @classmethod
    def create(
        cls,
        *,
        seat_id: int,
        seat_seq: str,
        status: SeatStatus,
    ) -> "PerformanceSeat":
        """등급에 속한 신규 좌석을 만든다. 상태는 생성 호출부가 전달한다."""
        return cls(seat_id=seat_id, seat_seq=seat_seq, status=status)

    # 2) 공백·길이를 기준으로 좌석명 검사
    @staticmethod
    def validate_seat_seq(seat_seq: str) -> None:
        if not isinstance(seat_seq, str) or not seat_seq.strip() or len(seat_seq) > 255:
            raise ValidationException("좌석명은 공백이 아닌 1~255자여야 합니다.")


# 교안처럼 공통 예외만 재사용한다. DB·예매·결제 구현에는 의존하지 않는다.
class SeatReservationConflictError(ConflictException):
    def __init__(self, message: str):
        super().__init__(message, error_code="SEAT_RESERVATION_CONFLICT")


@dataclass(frozen=True, kw_only=True)
class SeatIdentity:
    """예매용 단건 조회에 사용하는 회차·좌석 식별 값."""

    perf_id: int
    perf_seat_id: int

    def __post_init__(self) -> None:
        if any(
            type(value) is not int or not 0 < value <= 9223372036854775807
            for value in (self.perf_id, self.perf_seat_id)
        ):
            raise ValidationException(
                "회차·좌석 번호는 유효한 양수여야 합니다.",
                error_code="INVALID_SEAT_RESERVATION_ID",
            )


@dataclass(frozen=True, kw_only=True)
class SeatReservationChange:
    """예매에서 전달한 좌석 연결·해제 요청. 실제 상태 경합은 저장소 UPDATE가 검사한다."""

    perf_id: int
    perf_seat_id: int
    reserv_id: int
    expected_status: str
    target_status: str
    action: SeatReservationAction

    def __post_init__(self) -> None:
        if any(
            type(value) is not int or not 0 < value <= 9223372036854775807
            for value in (self.perf_id, self.perf_seat_id, self.reserv_id)
        ):
            raise ValidationException(
                "회차·좌석·예매 번호는 양수여야 합니다.",
                error_code="INVALID_SEAT_RESERVATION_ID",
            )
        if (
            not self.expected_status
            or not self.target_status
            or self.expected_status == self.target_status
        ):
            raise ValidationException(
                f"{self.action} 전후의 서로 다른 좌석 상태가 필요합니다.",
                error_code="INVALID_SEAT_STATUS_TRANSITION",
            )

    @classmethod
    def assign(
        cls,
        *,
        perf_id: int,
        perf_seat_id: int,
        reserv_id: int,
        expected_status: str,
        reserved_status: str,
    ) -> "SeatReservationChange":
        return cls(
            perf_id=perf_id,
            perf_seat_id=perf_seat_id,
            reserv_id=reserv_id,
            expected_status=expected_status,
            target_status=reserved_status,
            action=SeatReservationAction.ASSIGN,
        )

    @classmethod
    def release(
        cls,
        *,
        perf_id: int,
        perf_seat_id: int,
        reserv_id: int,
        expected_status: str,
        released_status: str,
    ) -> "SeatReservationChange":
        return cls(
            perf_id=perf_id,
            perf_seat_id=perf_seat_id,
            reserv_id=reserv_id,
            expected_status=expected_status,
            target_status=released_status,
            action=SeatReservationAction.RELEASE,
        )

    def require_applied(self, applied: bool) -> None:
        if not applied:
            message = (
                "좌석을 예매에 연결할 수 없습니다."
                if self.action == SeatReservationAction.ASSIGN
                else "좌석의 예매 연결을 해제할 수 없습니다."
            )
            raise SeatReservationConflictError(message)
