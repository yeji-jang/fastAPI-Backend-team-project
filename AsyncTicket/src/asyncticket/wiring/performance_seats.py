# <의존성 연결 - 개별 좌석 서비스>
# - 요청 또는 예매 호출부의 같은 세션으로 두 좌석 저장소와 서비스를 구성한다.

from typing import Annotated, Any, Callable

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from asyncticket.seats.application.service import PerformanceSeatService
from asyncticket.seats.infrastructure.repositories import (
    SqlAlchemyPerformanceSeatRepository,
    SqlAlchemySeatInfoRepository,
)


# 1) 라우터가 요청할 주입 지점
def provide_performance_seat_service() -> PerformanceSeatService:
    raise RuntimeError("좌석 조회 서비스 연결이 필요합니다.")


# 2) 조회·예매 연결·해제에 쓸 동일 세션 서비스 구성
def create_performance_seat_service(session: AsyncSession) -> PerformanceSeatService:
    return PerformanceSeatService(
        SqlAlchemyPerformanceSeatRepository(session),
        SqlAlchemySeatInfoRepository(session),
    )


# 3) 기본 주입 지점을 실제 서비스 생성 함수로 교체
def wire_dependencies(
    app: FastAPI,
    db_dependency: Callable[..., Any] | None = None,
) -> None:
    if db_dependency is None:
        from asyncticket.shared.core.database import get_db

        db_dependency = get_db

    # 4) 요청 세션으로 개별 좌석 서비스 생성
    def performance_seat_service(
        session: Annotated[AsyncSession, Depends(db_dependency)],
    ) -> PerformanceSeatService:
        return create_performance_seat_service(session)

    app.dependency_overrides[provide_performance_seat_service] = (
        performance_seat_service
    )
