"""
예매 요청·응답 모델 (Pydantic)
    1) 요청 스키마 : 
        - 클라이언트가 보내는 값을 받아 모양을 검사
        - 예매자 ID는 받지 않고 로그인 정보에서 가져온다
    2) 응답 스키마 : 
        - 예매 엔티티를 API로 내보낼 모양으로 바꾼다
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from asyncticket.reservations.domain.enums import ReservationStatus
from asyncticket.reservations.domain.reservation import Reservation


# ---------- 요청 ----------

class ReservationCreateRequest(BaseModel):
    """예매하기 요청 : 회차와 좌석만 받는다"""
    perf_id: int = Field(gt=0, description="회차 ID")
    perf_seat_id: int = Field(gt=0, description="개별 좌석 ID")


# ---------- 응답 ----------

class ReservationResponse(BaseModel):
    """예매 응답"""
    reserv_id: int = Field(description="예매 ID")
    order_number: str = Field(description="주문번호 (토스 orderId)")
    perf_id: int = Field(description="회차 ID")
    perf_seat_id: int | None = Field(description="개별 좌석 ID (좌석 연결이 없으면 null)")
    pay_id: int | None = Field(description="결제 ID (결제 전이면 null)")
    quantity: int = Field(description="예매 수량")
    total_amount: Decimal = Field(description="예매 금액")
    status: ReservationStatus = Field(description="예매 상태 (PENDING / CONFIRMED / CANCELED)")
    created_at: datetime | None = Field(description="예매 일시")
    confirmed_at: datetime | None = Field(description="확정 일시")
    canceled_at: datetime | None = Field(description="취소 일시")

    @classmethod
    def from_entity(cls, reservation: Reservation) -> "ReservationResponse":
        """
        예매 엔티티(VO 포함) → 응답 모델 (VO 안의 값을 꺼내 평평하게 만든다)
        """
        return cls(
            reserv_id=reservation.reserv_id,
            order_number=reservation.order_number,
            perf_id=reservation.performance.reserved_perf_id,
            perf_seat_id=reservation.seat.reserved_seat_id,
            pay_id=reservation.payment.reserved_pay_id if reservation.payment else None,
            quantity=reservation.quantity,
            total_amount=reservation.total_amount,
            status=reservation.status,
            created_at=reservation.created_at,
            confirmed_at=reservation.confirmed_at,
            canceled_at=reservation.canceled_at,
        )
