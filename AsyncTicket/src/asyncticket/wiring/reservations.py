# <의존성 연결 - 예매 서비스>
# - 요청 세션 하나로 예매 저장소·조회 구현·좌석 배정 어댑터를 만들어 ReservationService에 꽂는다.
# - 같은 세션을 쓰므로 예매 저장 → 좌석 연결이 한 트랜잭션으로 묶인다 (실패하면 get_db가 전체 rollback).

from typing import Annotated, Any, Callable

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from asyncticket.reservations.application.service import ReservationService
from asyncticket.reservations.infrastructure.repositories import SqlAlchemyReservationRepository
from asyncticket.reservations.infrastructure.services import (
    SqlAlchemyReservationChecker,
    SqlAlchemyReservedPerformanceReader,
    SqlAlchemyReservedSeatReader,
)
from asyncticket.reservations.infrastructure.adapter_seat_allocation import SeatAllocationAdapter
from asyncticket.wiring.performance_seats import create_performance_seat_service


# 1) 라우터가 요청할 주입 지점
def provide_reservation_service() -> ReservationService:
    raise RuntimeError("예매 서비스 연결이 필요합니다.")


# 2) 같은 세션으로 부품을 만들어 예매 서비스 조립
def create_reservation_service(session: AsyncSession) -> ReservationService:
    return ReservationService(
        repository=SqlAlchemyReservationRepository(session),
        checker=SqlAlchemyReservationChecker(session),
        performance_reader=SqlAlchemyReservedPerformanceReader(session),
        seat_reader=SqlAlchemyReservedSeatReader(session),
        seat_allocation=SeatAllocationAdapter(create_performance_seat_service(session)),
    )


# 3) 기본 주입 지점을 실제 서비스 생성 함수로 교체
def wire_dependencies(
    app: FastAPI, db_dependency: Callable[..., Any] | None = None,
) -> None:
    if db_dependency is None:
        from asyncticket.shared.core.database import get_db

        db_dependency = get_db

    # 4) 요청 세션으로 예매 서비스 생성
    def reservation_service(session: Annotated[AsyncSession, Depends(db_dependency)]) -> ReservationService:
        return create_reservation_service(session)

    app.dependency_overrides[provide_reservation_service] = reservation_service
