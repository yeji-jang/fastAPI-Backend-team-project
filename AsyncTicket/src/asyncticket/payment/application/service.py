"“”응용 계층: 결제 조회와 상태 변경 순서를 조율한다.“”"
from payment.domain.repository import PaymentRepository
from payment.domain.service import PaymentProcess
from payment.domain.payment import Payment
from payment.domain.exceptions import PaymentNotFoundException

class PaymentService:

    def __init__(self, payment_repo: PaymentRepository, processor: PaymentProcess):
        self.payment_repo = payment_repo
        self.processor = processor 


    # 결제 등록 (예약 등록 직후 함께 호출)
    async def create_payment(self, reserv_id: int, amount: int):
        payment = Payment.create(reserv_id, amount)
        await payment_repo.save(payment)

    # 결제 승인
    async def approve_payment(self, payment_key: str, reserv_id: int, amount: int):
        payment = await self.get_payment(reserv_id)
        payment.approve(payment_key, reserv_id, amount, self.processor)


    # 결제 취소
    async def cancel_payment(self, reserv_id: int, reason: str):
        payment = await self.get_payment(reserv_id)
        payment.cancel(reason)

    # 예약 ID로 결제정보 조회
    async def get_payment(reserv_id: int) -> Payment:
        payment = await payment_repo.find_by_reserv_id(reserv_id)
        if not payment:
            raise PaymentNotFoundException

        return payment