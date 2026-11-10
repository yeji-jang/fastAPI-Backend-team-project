"""
결제 요청·응답 모델 (Pydantic)
    1) 요청 스키마 :
        - 클라이언트가 보내는 값을 받아 모양을 검사
        - 결제자 ID는 받지 않고 로그인 정보에서 가져온다
        - 결제 시작은 금액을 받지 않는다 (서버가 예매 금액으로 정한다 → 변조 방지)
    2) 응답 스키마 :
        - 결제 엔티티를 API로 내보낼 모양으로 바꾼다
        - paymentKey는 내보내지 않는다 (환불에만 쓰는 내부 값)
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

# <Domain - 결제>
from asyncticket.payment.domain.enums import PaymentStatus # 결제 상태
from asyncticket.payment.domain.payment import Payment # 결제 엔티티


# ---------- 요청 ----------

class PaymentStartRequest(BaseModel):
    reserv_id: int = Field(gt=0, description="결제할 예매 ID. 금액은 서버가 예매 금액으로 정한다.")


class PaymentApproveRequest(BaseModel):
    payment_key: str = Field(min_length=1, max_length=200, description="토스가 결제창 성공 URL로 준 paymentKey")
    order_id: str = Field(min_length=6, max_length=64, description="결제 시작 응답의 order_id (토스 orderId)")
    amount: Decimal = Field(gt=0, description="토스가 결제창 성공 URL로 준 amount. 서버 금액과 다르면 거절")


# ---------- 응답 ----------

class PaymentResponse(BaseModel):
    pay_id: int = Field(description="결제 ID")
    reserv_id: int = Field(description="예매 ID")
    order_id: str = Field(description="토스 orderId (결제창 요청에 그대로 사용)")
    amount: Decimal = Field(description="결제 금액")
    status: PaymentStatus = Field(description="결제 상태 (READY, DONE, FAIL, REFUND)")
    method: str = Field(description="결제 수단. 승인 전에는 TOSS")
    paid_at: datetime | None = Field(None, description="결제 승인 일시")
    refunded_at: datetime | None = Field(None, description="환불 일시")

    @classmethod
    def from_entity(cls, payment: Payment, order_id: str) -> "PaymentResponse":
        """
        결제 엔티티 → 응답 모델 (order_id는 엔티티에 없어 서비스가 만들어 넘긴다)
        """
        assert payment.pay_id is not None
        return cls(
            pay_id=payment.pay_id,
            reserv_id=payment.reserv_id,
            order_id=order_id,
            amount=payment.amount,
            status=payment.status,
            method=payment.method,
            paid_at=payment.paid_at,
            refunded_at=payment.refunded_at,
        )
