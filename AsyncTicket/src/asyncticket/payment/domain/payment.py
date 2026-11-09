"""
<결제규칙>
- 결제 자신의 값으로 판단할 수 있는 규칙만 담음 (상태 규칙만 판단하고, 외부 호출·저장은 하지 않는다)
- FastAPI, SQLAlchemy, 토스(httpx), 다른 도메인(예매·좌석)을 import하지 않음
- 토스 호출 순서는 응용 서비스(application/service.py)가 정한다
    → 엔티티는 "지금 승인해도 되는가 / 환불해도 되는가"만 판단하고 상태를 바꾼다

<흐름 (2026-11-09 기준)>
1. 예매대기(PENDING)가 먼저 생긴다 (예매 담당).
2. 결제 시작: 예매 1건당 결제 1건을 READY로 만든다. 금액은 예매 금액을 서버가 쓴다.
3. 결제창 → 프론트가 (paymentKey, orderId, amount)로 승인 요청.
4. 승인: 금액 대조 → 결제 DONE·예매 확정을 DB에 반영 → 토스 승인 호출(마지막).
   토스가 실패하면 요청 전체가 rollback되어 READY·PENDING으로 남는다.
5. 환불: 예매 취소가 내부에서 호출한다. 결제 REFUND 반영 → 토스 취소 호출(마지막).
6. 재시도: 같은 예매로 새 결제(새 orderId)를 만들지 않는다. 처리된 결제가 있으면 다시 시작할 수 없다.

<도메인 비즈니스 요구사항 정의>
    1) 결제는 4가지 상태로 관리 (enums.py)
        - 결제대기(READY), 결제완료(DONE), 결제실패(FAIL), 환불완료(REFUND)
    2) 결제 시작 (create)
        - 결제 금액은 0원보다 커야 한다
        - 생성되면 결제대기(READY), 결제수단은 승인 전까지 "TOSS"
    3) 결제 승인 반영 (mark_paid)
        - 결제대기(READY) 상태에서만 승인할 수 있다
        - 요청 금액이 결제 금액과 다르면 거절 (금액 변조 → 토스를 호출하지 않는다)
        - paymentKey는 필수
        - 승인되면 결제완료(DONE)가 되고 paymentKey와 승인 일시를 기록한다
    4) 환불 반영 (mark_refunded)
        - 결제완료(DONE) 상태에서만 환불할 수 있다
        - paymentKey가 있어야 토스에 취소를 요청할 수 있다
        - 취소 사유는 필수
        - 환불되면 환불완료(REFUND)가 되고 환불 일시를 기록한다
    5) 토스 응답 기록 (record)
        - 승인·취소 응답을 순서대로 쌓는다
        - 승인 응답에 결제수단이 있으면 결제수단을 바꾼다
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal # amount

# <Domain - 결제>
from asyncticket.payment.domain.enums import PaymentStatus # 요구사항 1번
from asyncticket.payment.domain.exceptions import (
    PaymentAmountInvalidException,  # 금액 불일치 (400)
    PaymentException,               # 필수 값 없음 (400)
    PaymentStatusException,         # 상태 때문에 불가 (409)
)
from asyncticket.payment.domain.payment_log import PaymentLog # 토스 응답 1건 (VO)

# 1. 상수
# payments.method는 NOT NULL이라 승인 전에는 결제사 이름을 넣고, 승인 후 토스가 준 수단으로 바꾼다.
METHOD_BEFORE_APPROVAL = "TOSS"


# 2. 엔터티
@dataclass
class Payment:
    """결제 엔티티 (예매 1건 = 결제 1건)"""
    # 1) 결제 자신의 정보
    reserv_id: int                          # 연결된 예매 (orderId도 이 값으로 만든다)
    amount: Decimal                         # 결제 금액 = 예매 금액
    pay_id: int | None = None               # DB 저장 전에만 None, 저장 후에는 항상 값이 있음
    status: PaymentStatus = PaymentStatus.READY
    payment_key: str | None = None          # 토스 paymentKey (승인 후 생김, 환불에 필요)
    method: str = METHOD_BEFORE_APPROVAL    # 결제수단 (승인 후 토스 응답 값)

    # 2) 일시 (상태가 바뀐 시각)
    created_at: datetime | None = None      # DB에 저장되기 전에는 생성일이 없다
    paid_at: datetime | None = None
    refunded_at: datetime | None = None

    # 3) 토스 응답 기록 (인스턴스마다 새 리스트 → 결제끼리 기록이 섞이지 않는다)
    logs: list[PaymentLog] = field(default_factory=list)

    # 4) 새 결제를 만드는 방법 (결제 시작 → 결제대기) : 요구사항 2번
    @classmethod
    def create(cls, reserv_id: int, amount: Decimal) -> "Payment":
        """결제 시작 (READY)"""
        # 1) 금액은 0원보다 커야 한다
        if amount <= 0:
            raise PaymentAmountInvalidException("결제 금액은 0원보다 커야 합니다.")
        return cls(reserv_id=reserv_id, amount=amount)

    # 5) 결제 승인 반영 : 요구사항 3번
    def mark_paid(self, *, payment_key: str, amount: Decimal, now: datetime) -> None:
        """승인 반영. 토스 호출 전에 규칙을 먼저 확인한다."""
        # 1) 결제대기(READY) 상태에서만 승인할 수 있다
        if self.status != PaymentStatus.READY:
            raise PaymentStatusException("결제대기 상태에서만 승인할 수 있습니다.")
        # 2) 금액이 다르면 거절 (변조)
        if Decimal(amount) != self.amount:
            raise PaymentAmountInvalidException()
        # 3) paymentKey는 필수
        if not payment_key or not payment_key.strip():
            raise PaymentException("paymentKey는 필수입니다.", error_code="PAYMENT_KEY_REQUIRED")
        # 4) 승인되면 결제완료(DONE), paymentKey·승인 일시 기록
        self.status = PaymentStatus.PAID
        self.payment_key = payment_key
        self.paid_at = now

    # 6) 환불 반영 : 요구사항 4번
    def mark_refunded(self, *, reason: str, now: datetime) -> None:
        """환불 반영. 토스 호출 전에 규칙을 먼저 확인한다."""
        # 1) 결제완료(DONE) 상태에서만 환불할 수 있다
        if self.status != PaymentStatus.PAID:
            raise PaymentStatusException("결제완료 상태에서만 환불할 수 있습니다.")
        # 2) paymentKey가 있어야 토스에 취소를 요청할 수 있다
        if not self.payment_key:
            raise PaymentException("paymentKey가 없어 환불할 수 없습니다.", error_code="PAYMENT_KEY_REQUIRED")
        # 3) 취소 사유는 필수
        if not reason or not reason.strip():
            raise PaymentException("취소 사유는 필수입니다.", error_code="CANCEL_REASON_REQUIRED")
        # 4) 환불되면 환불완료(REFUND), 환불 일시 기록
        self.status = PaymentStatus.REFUNDED
        self.refunded_at = now

    # 7) 토스 응답 기록 : 요구사항 5번
    def record(self, log: PaymentLog) -> None:
        """토스 응답 기록. 승인 응답에 결제수단이 있으면 반영한다."""
        # 1) 응답을 순서대로 쌓는다
        self.logs.append(log)
        # 2) 결제수단이 있으면 바꾼다 (payments.method 길이 50자)
        method = log.value.get("method")
        if isinstance(method, str) and method:
            self.method = method[:50]
