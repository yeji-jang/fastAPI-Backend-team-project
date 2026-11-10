# <의존성 연결 - 좌석 등급 서비스>
# - 요청 세션 → 등급·개별 좌석 저장소 → SeatInfoService 순서로 연결한다.

from typing import Annotated, Any, Callable

from fastapi import Depends, FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncSession

from asyncticket.seats.application.service import SeatInfoService
from asyncticket.seats.application.ports import SeatListCache
from asyncticket.wiring.performance_seats import provide_seat_list_cache
from asyncticket.shared.domain.catalog import CatalogPolicy
from asyncticket.seats.infrastructure.repositories import (
    SqlAlchemyPerformanceSeatRepository,
    SqlAlchemySeatInfoRepository,
)


# 1) 라우터가 요청할 주입 지점
def provide_seat_info_service() -> SeatInfoService:
    raise RuntimeError("좌석 구성 서비스 연결이 필요합니다.")


# 2) 같은 세션의 저장소와 권한 정책으로 서비스 구성
def create_seat_info_service(
    session: AsyncSession,
    policy: CatalogPolicy | None = None,
    *,
    seat_list_cache: SeatListCache | None = None,
) -> SeatInfoService:
    """등급 저장소·좌석 저장소·트랜잭션에 같은 세션을 주입한다."""
    return SeatInfoService(
        repository=SqlAlchemySeatInfoRepository(session),
        performance_seat_repository=SqlAlchemyPerformanceSeatRepository(session),
        policy=policy if policy is not None else CatalogPolicy(),
        seat_list_cache=seat_list_cache,
    )


# 3) 기본 주입 지점을 실제 서비스 생성 함수로 교체
def wire_dependencies(
    app: FastAPI,
    db_dependency: Callable[..., Any] | None = None,
) -> None:
    if db_dependency is None:
        from asyncticket.shared.core.database import get_db

        db_dependency = get_db

    # 4) 요청 세션·앱 정책을 서비스 생성 함수에 전달
    def seat_info_service(
        request: Request,
        session: Annotated[AsyncSession, Depends(db_dependency)],
        cache: Annotated[SeatListCache | None, Depends(provide_seat_list_cache)],
    ) -> SeatInfoService:
        return create_seat_info_service(
            session,
            getattr(request.app.state, "catalog_policy", CatalogPolicy()),
            seat_list_cache=cache,
        )

    app.dependency_overrides.update(
        {
            provide_seat_info_service: seat_info_service,
        }
    )
