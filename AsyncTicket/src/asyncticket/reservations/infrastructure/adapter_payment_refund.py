"""
결제 환불 어댑터 (application/ports.py의 PaymentRefund 구현)
    - 예매 application의 "환불해줘" 요청을 결제 서비스 호출로 바꿔 준다
    - 결제 담당 코드는 수정하지 않고, 공개된 결제 서비스 메서드만 호출한다
        refund_for_reservation(reserv_id, reason) : 결제 REFUNDED 저장 → 토스 취소(마지막)
    - 결제 쪽 예외(결제 없음 404, 환불 불가 409, 토스 실패 400/502)는 바꾸지 않고 그대로 올려 보낸다
    - 결제 서비스는 만드는 함수로 받는다
        결제 서비스가 예매 서비스를 품고 있어서, 미리 만들면 서로가 서로를 계속 만들게 된다
        → 환불이 실제로 필요할 때 한 번만 만든다
    - 같은 구조 : adapter_seat_allocation.py (좌석 서비스를 감쌈)
"""

from typing import Callable

# <Application - 예매>
from asyncticket.reservations.application.ports import PaymentRefund

# <결제 도메인 - 호출만 한다>
from asyncticket.payment.application.service import PaymentService

class PaymentRefundAdapter(PaymentRefund):

    def __init__(self, payment_service_factory: Callable[[], PaymentService]):
        self.payment_service_factory = payment_service_factory

    # 환불 : 예매에 연결된 결제를 환불
    async def refund(
            self,
            *, 
            reserv_id : int,
            reason : str) -> None :
        payment_service = self.payment_service_factory()
        await payment_service.refund_for_reservation(reserv_id=reserv_id, reason=reason)