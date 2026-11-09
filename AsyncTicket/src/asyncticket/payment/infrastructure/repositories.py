"""
결제 저장소 구현
    - domain/repository.py의 약속을 SQLAlchemy로 구현
        1) 결제 ID로 찾고
        2) 예매 ID로 찾고 (예매 1건 = 결제 1건, 과거 데이터가 여러 건이면 가장 최근 것)
        3) 새 결제를 저장하거나 바뀐 상태(승인, 환불)를 저장
    - commit은 하지 않는다 :
        - 요청이 끝날 때 get_db가 commit
        - 결제 저장 → 예매 확정 → 토스 호출을 한 트랜잭션으로 묶기 위해 flush만 한다
    - DB 행 ↔ 도메인 엔티티 변환은 아래 함수 두 개(_log_json, _to_domain)에서만 한다
"""

from typing import Any

# <SQLAlchemy>
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# <Domain - 결제>
from asyncticket.payment.domain.enums import PaymentStatus # 결제 상태
from asyncticket.payment.domain.payment import Payment # 결제 엔티티
from asyncticket.payment.domain.payment_log import PaymentLog # 토스 응답 1건
from asyncticket.payment.domain.repository import PaymentRepository # (추상)결제 저장소

# <InfraStructure - 결제>
from asyncticket.payment.infrastructure.models import Payment as PaymentModel # 결제 모델 - payments 테이블

# payments 테이블에 paymentKey 컬럼이 없어 payment_log(JSONB)에 함께 보관한다.
#   {"payment_key": "<토스 paymentKey>", "logs": [<토스 응답>, ...]}


# 1. 결제 저장소
class SqlAlchemyPaymentRepository(PaymentRepository):
    def __init__(self, db: AsyncSession):
        self.db = db    # 요청 세션 (예매와 같은 세션)

    # 1) 결제 ID로 조회
    async def find_by_id(self, pay_id: int) -> Payment | None:
        stmt = select(PaymentModel).where(PaymentModel.pay_id == pay_id)
        row = (await self.db.execute(stmt)).scalar_one_or_none()
        return None if row is None else _to_domain(row)

    # 2) 예매 ID로 조회
    async def find_by_reserv_id(self, reserv_id: int) -> Payment | None:
        """예약 ID로 결제 조회. 예매 1건 = 결제 1건이지만, 과거 데이터가 여러 건이면 가장 최근 것."""
        stmt = (
            select(PaymentModel)
            .where(PaymentModel.reserv_id == reserv_id)
            .order_by(PaymentModel.created_at.desc(), PaymentModel.pay_id.desc())
            .limit(1)
        )
        row = (await self.db.execute(stmt)).scalar_one_or_none()
        return None if row is None else _to_domain(row)

    # 3) 저장
    async def save(self, payment: Payment) -> None:
        # commit은 get_db가 요청 끝에 한다. flush로 SQL만 보내 pay_id를 받는다.
        # 3-1) 새 결제 : INSERT 후 pay_id·created_at을 엔티티에 채운다
        if payment.pay_id is None:
            row = PaymentModel(
                reserv_id=payment.reserv_id,
                method=payment.method,
                amount=payment.amount,
                status=payment.status.value,
                paid_at=payment.paid_at,
                refunded_at=payment.refunded_at,
                payment_log=_log_json(payment),
            )
            if payment.created_at is not None:
                row.created_at = payment.created_at
            self.db.add(row)
            await self.db.flush()
            payment.pay_id = row.pay_id
            payment.created_at = row.created_at
            return

        # 3-2) 기존 결제 : 행을 찾아 바뀐 값을 덮어쓴다
        stmt = select(PaymentModel).where(PaymentModel.pay_id == payment.pay_id)
        row = (await self.db.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise LookupError(f"저장할 결제가 없습니다: pay_id={payment.pay_id}")
        row.reserv_id = payment.reserv_id
        row.method = payment.method
        row.amount = payment.amount
        row.status = payment.status.value
        row.paid_at = payment.paid_at
        row.refunded_at = payment.refunded_at
        row.payment_log = _log_json(payment)  # 새 dict를 넣어야 JSONB 변경이 감지된다
        await self.db.flush()


# 2. 변환 : 엔티티 → payment_log(JSONB)
def _log_json(payment: Payment) -> dict[str, Any]:
    return {"payment_key": payment.payment_key, "logs": [log.value for log in payment.logs]}


# 3. 변환 : DB 행 → 엔티티
def _to_domain(row: PaymentModel) -> Payment:
    # DB 컬럼은 nullable(팀 결정)이지만, 결제 엔티티는 항상 예매에 연결된다.
    if row.reserv_id is None:
        raise LookupError(f"예매가 연결되지 않은 결제입니다: pay_id={row.pay_id}")
    data = row.payment_log or {}
    return Payment(
        pay_id=row.pay_id,
        reserv_id=row.reserv_id,
        amount=row.amount,
        status=PaymentStatus(row.status),
        payment_key=data.get("payment_key"),
        method=row.method,
        created_at=row.created_at,
        paid_at=row.paid_at,
        refunded_at=row.refunded_at,
        logs=[PaymentLog(value=v) for v in data.get("logs", [])],
    )
