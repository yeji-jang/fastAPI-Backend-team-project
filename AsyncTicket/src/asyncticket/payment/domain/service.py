"""
<외부 결제사 호출 약속 (추상화)>
- 결제 도메인·응용 계층은 토스를 직접 알지 않고 이 약속만 사용한다
- 실제 구현 : infrastructure/toss.py (TossPaymentProcess)
    → 테스트에서는 가짜 구현으로 바꿔 끼워 토스 없이 검증한다
- 실패하면 PaymentGatewayException을 던진다 (응용 서비스는 이 예외로 요청 전체를 rollback시킨다)
"""

from abc import ABC, abstractmethod
from decimal import Decimal # 결제 금액

# <Domain - 결제>
from asyncticket.payment.domain.payment_log import PaymentLog # 토스 응답 1건


# 1. 결제사 호출 약속
class PaymentProcess(ABC):
    """외부 결제사(토스) 호출 약속. 실패하면 PaymentGatewayException을 던진다."""

    # 1) 결제 승인 : 결제창에서 받은 paymentKey·orderId·금액으로 실제 결제를 확정한다
    @abstractmethod
    async def approve(self, *, payment_key: str, order_id: str, amount: Decimal) -> PaymentLog:
        ...

    # 2) 결제 취소(환불) : 승인된 결제를 전액 환불한다
    @abstractmethod
    async def cancel(self, *, payment_key: str, reason: str) -> PaymentLog:
        ...
