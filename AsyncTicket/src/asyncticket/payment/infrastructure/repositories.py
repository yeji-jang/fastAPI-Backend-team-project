from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from asyncticket.payment.domain.payment import Payment
from asyncticket.payment.domain.enums import PaymentStatus
from asyncticket.payment.domain.repository import PaymentRepository
from asyncticket.payment.infrastructure.models import Payment as PaymentModel


class SqlAlchemyPaymentRepository(PaymentRepository):
    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_by_id(self, pay_id: int) -> Payment | None:
        stmt = select(PaymentModel).where(PaymentModel.pay_id == pay_id)
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return Payment(
            pay_id = row.pay_id,
            method = row.method,
            amount = row.amount,
            status = PaymentStatus(row.status),
            reserv_id = row.reserv_id,
            created_at = row.created_at,
            paid_at = row.paid_at,
            refunded_at = row.refunded_at,
        )

    async def find_by_reserv_id(self, reserv_id: int) -> Payment | None:
    """예약 ID로 결제 정보 조회"""

    async def save(self, payment: Payment) -> None:
        if payment.pay_id is None:
            row = PaymentModel(
                reserv_id = payment.reserv_id,
                method = payment.method,
                amount = payment.amount,
                status = payment.status.value,
                paid_at = payment.paid_at,
                refunded_at = payment.refunded_at,
            )
            if payment.created_at is not None:
                row.created_at = payment.created_at
            self.db.add(row)
            # commit은 get_db가 요청 끝에 한다. flush로 INSERT만 보내 pay_id를 받는다.
            await self.db.flush()
            payment.pay_id = row.pay_id
            payment.created_at = row.created_at
            return
        stmt = select(PaymentModel).where(PaymentModel.pay_id == payment.pay_id)
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            raise LookupError(f"저장할 결제가 없습니다: pay_id={payment.pay_id}")
        row.reserv_id = payment.reserv_id
        row.method = payment.method
        row.amount = payment.amount
        row.status = payment.status.value
        row.paid_at = payment.paid_at
        row.refunded_at = payment.refunded_at
