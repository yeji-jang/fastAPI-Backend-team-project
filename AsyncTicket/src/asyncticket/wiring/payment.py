"""결제 저장소·토스 호출·예매 어댑터를 요청 세션 하나로 묶어 결제 서비스에 연결한다.

- 결제와 예매가 같은 세션을 쓰므로 결제 저장 → 예매 확정이 한 트랜잭션으로 묶인다.
  (get_db가 요청 끝에 commit, 예외가 나면 전체 rollback)
- TOSS_ORDER_PREFIX: 토스 orderId 접두어. 같은 토스 테스트 키를 쓰는 팀원끼리는 다르게 둔다.
"""

import os
from typing import Annotated, Any, Callable

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from asyncticket.payment.application.service import PaymentService
from asyncticket.payment.infrastructure.adapter_reservation import ReservationGatewayAdapter
from asyncticket.payment.infrastructure.repositories import SqlAlchemyPaymentRepository
from asyncticket.payment.infrastructure.toss import TossPaymentProcess
from asyncticket.payment.presentation.dependencies import provider_payment_service
from asyncticket.wiring.reservations import create_reservation_service


def create_payment_service(session: AsyncSession) -> PaymentService:
    return PaymentService(
        payment_repo=SqlAlchemyPaymentRepository(session),
        processor=TossPaymentProcess(),
        reservations=ReservationGatewayAdapter(create_reservation_service(session)),
        order_prefix=os.getenv("TOSS_ORDER_PREFIX", "reserv"),
    )


def wire_dependencies(
    app: FastAPI, db_dependency: Callable[..., Any] | None = None,
) -> None:
    if db_dependency is None:
        from asyncticket.shared.core.database import get_db

        db_dependency = get_db

    def payment_service(session: Annotated[AsyncSession, Depends(db_dependency)]) -> PaymentService:
        return create_payment_service(session)

    app.dependency_overrides[provider_payment_service] = payment_service
