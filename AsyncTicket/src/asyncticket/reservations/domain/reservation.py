"""
<예매규칙>
- 예매 자신의 값으로 판단할 수 있는 규칙만 담음
- FastAPI, SQLAlchemy, 다른 도메인(회원·회차·좌석·결제)을 import하지 않음
- 규칙에 필요한 외부 값은 VO로 전달받고, 판단은 예매가 한다

<도메인 비즈니스 요구사항 정의>
    1) 예매는 4가지 상태로 관리
        - 예매대기(PENDING), 예매확정(CONFIRMED), 예매취소(CANCELED), 예매만료(EXPIRED)
    2) 예매 생성 (예매하기)
        - 예매 1건에는 좌석수량 1개만 예매가능 (quantity = 1)
        - 예매 금액은 0원보다 커야 한다
        - 예매 기간 안에만 예매 (예매 시작일시 <= 현재(now) < 예매 마감 일시)
        - 판매 가능한 좌석만 예매할 수 있다 (좌석 도메인 assign_reservation에서 보장)
        - 생성되면 예매대기(PENDING), DB 저장 시 reserv_id가 생긴다
        - 한 회원은 한 회차에 예매대기·예매확정 예매를 1건만 가질 수 있다 (취소하면 다시 가능)
        - 주문번호는 생성할 때 "ORD-"로 시작하는 고유 번호로 만든다 (토스 orderId로 사용)
    3) 예매 확정 (결제 성공 후)
        - 예매대기(PENDING) 상태에서만 확정 가능
        - 결제 대기 시간(5분)이 지나면 확정할 수 없다
        - 확정되면 예매확정(CONFIRMED)이 되고 결제 정보와 확정 일시를 기록한다
        - 결제 성공 여부는 결제 도메인이 판단
    4) 예매 조회
        - 본인 예매만 조회
        - 예매ID, 회원ID, 회차ID, 예매수량, 금액, 상태, 예매·확정·취소 일시를 확인할 수 있다
    5) 예매 취소
        - 본인 예매만 취소
        - 예매확정(CONFIRMED) 상태에서만 취소 가능
        - 공연 시작 전까지만 취소
        - 취소처리되면 예매상태는 취소(CANCELED)가 되고 취소 일시를 기록한다
    6) 예매대기 만료
        - 예매대기(PENDING) 상태에서 생성 후 5분이 지나면 만료할 수 있다
        - 만료되면 예매상태는 예매만료(EXPIRED)가 된다
        - 만료된 예매는 1인 1건에 포함되지 않아 다시 예매할 수 있다
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal # total_amount

from asyncticket.reservations.domain.enums import ReservationStatus # 요구사항 1번

# 1. 예매 예외
class ReservationError(Exception):
    """예매 도메인 예외의 공통부모"""
    def __init__(self, message:str, error_code:str):
        self.message = message  
        self.error_code = error_code
        super().__init__(message)

class ReservationValidationError(ReservationError):
    """
    값이 예매 규칙에 맞지 않을때 발생되는 오류
    - 좌석 선택 수량이 1을 초과
    - 좌석 금액이 0보다 작음
    - 바뀔 HTTP 상태 : 422
    """

class ReservationForbiddenError(ReservationError):
    """
    본인 예매가 아님을 알리는 오류
    - 바뀔 HTTP 상태 : 403
    """


class ReservationNotFoundError(ReservationError):
    """
    찾는 대상이 없음
    - 예매 없음
    - 회차 없음
    - 해당 회차의 좌석 없음
    - 바뀔 HTTP 상태 : 404
    """

class ReservationConflictError(ReservationError):
    """
    현재 상태에서는 할수없음을 의미
    - 예매 기간이 아님
    - 판매된 좌석 -> 좌석 도메인이 관리!
    - 예매대기 상태가 아님 (확정 불가)
    - 확정된 예매가 아님 (취소 불가)
    - 공연이 시작됨
    - 바뀔 HTTP 상태 : 409
    """


# 결제 대기 시간
# - 예매대기 후 이 시간 안에 결제하지 않으면 예매대기 상태가 만료됨
# - 결제 : 토스페이먼츠에서 유효기간 사용하지 않아 예매 자체 규칙으로 관리
PENDING_EXPIRE_MINUTES = 5


# 2. VO(Value Object)
@dataclass(frozen=True, kw_only=True)
class TicketHolder:
    """예매자(users)"""
    ticketholder_id: int      # 본인 예매만 조회/취소
    # ticketholder_name: str  # 조회 응답에서 가져오기

@dataclass(frozen=True, kw_only=True)
class ReservedPerformance:
    """예매한 회차(performances)"""
    reserved_perf_id: int
    perf_starts_at: datetime   # 예매취소 : 공연 시작일 전까지
    reserv_opens_at: datetime  # 예매생성 : 예매 시작일부터
    reserv_closes_at: datetime # 예매생성 : 예매 마감일까지

@dataclass(frozen=True, kw_only=True)
class ReservedSeat:
    """예매한 좌석 정보 (performance_seats, seats_info)"""
    reserved_seat_id: int | None = None  # performance_seats.perf_seat_id (좌석 연결 전·취소 후 재판매 시 None 가능)      
    reserved_seat_price: Decimal # 예매생성 : 예매 금액 = 좌석

@dataclass(frozen=True, kw_only=True)
class ReservedPayment:
    """예매결제 (payments)"""
    reserved_pay_id:  int | None = None
    # is_paid: bool                 # 예매생성 : 결제 완료된 경우에만
    # is_linked: bool               # 예매생성 : 다른 예매에 이미 쓰인 결제는 불가
    # paid_amount: Decimal          # 예매생성 : 결제 금액 = 좌석 가격

# 3. 엔터티
@dataclass(kw_only=True)
class Reservation:
    """예매 엔티티 """
    # 1) VO 정보들
    ticketholder:TicketHolder
    performance:ReservedPerformance
    seat:ReservedSeat
    payment: ReservedPayment | None = None 

    # 2) 예매 자신의 정보
    order_number: str
    total_amount: Decimal
    status: ReservationStatus
    quantity: int = 1               # 1건 = 1좌석
    reserv_id: int | None = None    # DB 저장 전에만 None 저장 후에는 항상 값이 있음
    created_at: datetime | None=None # DB에 저장되기 전에는 생성일이 없다
    confirmed_at: datetime | None=None
    canceled_at: datetime | None=None

    # 3) 예매가 생성될 때마다 항상 검사하는 규칙 
    def __post_init__(self):
        # 예매 1건 = 좌석 1개
        if self.quantity != 1 :
            raise ReservationValidationError(
                message="예매 1건에는 좌석 1개만 예매할 수 있습니다",
                error_code="INVALID_QUANTITY"
            )

        # 금액은 0원보다 커야한다
        if self.total_amount <= 0 :
            raise ReservationValidationError(
                message="예매 금액은 0원보다 커야합니다",
                error_code="INVALID_TOTAL_AMOUNT"
            )

    # 4) 새 예매를 만드는 방법 (예매하기 → 예매대기)
    @classmethod
    def create_pending(
        cls,
        *, 
        ticketholder:TicketHolder, 
        performance:ReservedPerformance, 
        seat:ReservedSeat,
        has_active_reservation: bool,   # 이 회차에 진행 중(대기·확정) 예매가 있는지
        now: datetime) -> "Reservation": 

        # 예매생성 규칙
        # 1) 한 회원은 한 회차에 1건만
        if has_active_reservation :
            raise ReservationConflictError(
                message="이미 예매한 회차입니다",
                error_code="RESERVATION_ALREADY_EXISTS"
            )

        # 2) 예매 기간 안에만
        if not (performance.reserv_opens_at <= now < performance.reserv_closes_at):
            raise ReservationConflictError(
                message="예매 가능한 기간이 아닙니다",
                error_code="RESERVATION_NOT_OPEN"
            )

        return cls(
            ticketholder=ticketholder,
            performance=performance,
            seat=seat,
            order_number=f"ORD-{uuid.uuid4().hex}",  # 주문번호는 엔티티가 직접 생성
            total_amount=seat.reserved_seat_price,
            status=ReservationStatus.PENDING,   # 결제 전이므로 예매대기
        )

    # 5) 예매 확정 (결제 성공 후)
    def confirm(
            self,
            payment : ReservedPayment,
            now : datetime    
        ) -> None :

        # 1) 예매대기(PENDING) 상태에서만 확정 가능
        if self.status != ReservationStatus.PENDING :
            raise ReservationConflictError (
                message="예매대기(PENDING) 상태에서만 확정할 수 있습니다",
                error_code="RESERVATION_NOT_PENDING"
            )

        # 2) 결제 대기시간이 지났으면 예매를 확정할 수 없다
        if self.is_expired(now) :
            raise ReservationConflictError(
                message="결제 대기 시간이 지나 예매를 확정할 수 없습니다",
                error_code="RESERVATION_EXPIRED"
            )

        # 3) 확정하면 예매확정(CONFIRMED)이 되고 결제 정보와 확정 일시를 기록
        self.status = ReservationStatus.CONFIRMED
        self.payment = payment
        self.confirmed_at = now


    # 6) 본인 확인 (본인만 취소, 본인 예매만 조회)
    def is_owned(self, ticketholder_id: int) -> bool:
        return self.ticketholder.ticketholder_id == ticketholder_id

    # 7) 예매 조회 (본인 예매만 조회)
    def check_viewable(self, ticketholder_id:int) -> None :

        # 1) 본인 예매만 조회할 수 있다
        if not self.is_owned(ticketholder_id) :
            raise ReservationForbiddenError(
                message="본인의 예매만 조회할 수 있습니다.",
                error_code="RESERVATION_FORBIDDEN"
            )

    # 8) 예매 취소
    def cancel(self, ticketholder_id:int, now: datetime) -> None:

        # 1) 본인만 취소할 수 있다
        if not self.is_owned(ticketholder_id):
            raise ReservationForbiddenError(
                message="본인의 예매만 취소할 수 있습니다",
                error_code="RESERVATION_FORBIDDEN"
            )

        # 2) 예매확정(CONFIRMED) 상태에서만 가능
        if self.status != ReservationStatus.CONFIRMED :
            raise ReservationConflictError(
                message="확정된 예매만 취소할 수 있습니다",
                error_code="RESERVATION_NOT_CANCELABLE"
            )

        # 3) 공연 시작 전까지만 취소할 수 있다
        if now >= self.performance.perf_starts_at:
            raise ReservationConflictError(
                message="공연이 시작된 이후에는 취소할 수 없습니다",
                error_code="PERFORMANCE_ALREADY_STARTED"
            )

        # 4) 취소하면 예매 상태는 예매취소(CANCELED)가 되고 취소 일 기록(null -> date생성)
        self.status = ReservationStatus.CANCELED
        self.canceled_at = now

    # 9) 예매대기 만료 여부 (예매대기 상태에서 결제 대기 시간이 지났는지)
    def is_expired(self, now : datetime) -> bool :
        if self.status != ReservationStatus.PENDING or self.created_at is None :
            return False

        return now >= self.created_at + timedelta(minutes=PENDING_EXPIRE_MINUTES)

    # 10) 예매 만료 (결제하지 않고 시간이 지난 예매)
    def expire(self, now : datetime) -> None :

        # 1) 결제 대기 시간이 지난 예매대기만 만료할 수 있다
        if not self.is_expired(now) :
            raise ReservationConflictError(
                message="만료할 수 없는 예매입니다",
                error_code="RESERVATION_NOT_EXPIRABLE"
            )

        # 2) 만료하면 예매 상태는 예매만료(EXPIRED)
        self.status = ReservationStatus.EXPIRED