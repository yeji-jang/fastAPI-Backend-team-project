# <의존성 연결 - 예매 서비스>
# - 요청 세션 하나로 예매 저장소·조회 구현·좌석 배정 어댑터를 만들어 ReservationService에 꽂는다.
# - 같은 세션을 쓰므로 예매 저장 → 좌석 연결이 한 트랜잭션으로 묶인다 (실패하면 get_db가 전체 rollback).


import asyncio
from datetime import datetime, timezone
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

from asyncticket.shared.core.logger import get_logger

logger = get_logger("reservation.expiry")

# 만료 확인 주기 (초)
EXPIRE_CHECK_SECONDS = 60

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


# 5) 예매대기 만료 1회 실행 : 예매마다 트랜잭션을 나눠 처리
#    - HTTP 요청이 아니라서 get_db를 쓸 수 없으므로 세션을 직접 연다
#    - 예매 1건의 상태 변경 + 좌석 해제는 같은 트랜잭션 (둘 다 되거나 둘 다 취소)
#    - 한 건이 실패해도 그 건만 rollback 하고 나머지는 계속 처리한다
async def expire_pending_reservations(
    *,
    now: datetime | None = None,
    session_factory=None,
    service_factory: Callable[[AsyncSession], ReservationService] = create_reservation_service,
) -> int:
    if session_factory is None:
        from asyncticket.shared.core.database import AsyncSessionLocal

        session_factory = AsyncSessionLocal
    now = now or datetime.now(timezone.utc)

    # ① 만료 대상 ID만 먼저 찾는다 (조회만 하므로 commit 없음)
    async with session_factory() as session:
        reserv_ids = await service_factory(session).find_expired_pending(now=now)

    # ② 예매마다 새 세션(트랜잭션)으로 만료
    expired_count = 0
    for reserv_id in reserv_ids:
        async with session_factory() as session:
            try:
                if await service_factory(session).expire(reserv_id=reserv_id, now=now):
                    expired_count += 1
                await session.commit()      # 이 예매의 만료 상태 + 좌석 해제 확정
            except Exception:
                await session.rollback()    # 이 예매만 취소 (다음 주기에 다시 시도)
                logger.exception("예매대기 만료 실패 : reserv_id=%s", reserv_id)

    return expired_count


# 6) 1분마다 만료 반복 (서버가 켜져 있는 동안)
async def run_reservation_expiry(interval: float = EXPIRE_CHECK_SECONDS) -> None:
    while True:
        await asyncio.sleep(interval)       # 먼저 1분 기다린 뒤 확인
        try:
            count = await expire_pending_reservations()
            if count:
                logger.info("예매대기 %d건 만료 처리", count)
        except Exception:
            # 오류가 나도 반복은 멈추지 않는다 (다음 주기에 다시 시도)
            logger.exception("예매대기 만료 처리 실패")
