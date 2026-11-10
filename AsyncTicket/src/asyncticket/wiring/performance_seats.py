# <의존성 연결 - 개별 좌석 서비스>
# - 요청 또는 예매 호출부의 같은 세션으로 두 좌석 저장소와 서비스를 구성한다.

import logging
import os
from typing import Annotated, Any, AsyncIterator, Callable

from redis.asyncio import Redis
from redis.backoff import NoBackoff
from redis.retry import Retry
from redis.exceptions import RedisError

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from asyncticket.seats.application.service import PerformanceSeatService
from asyncticket.seats.application.ports import SeatListCache
from asyncticket.seats.infrastructure.cache import RedisSeatListCache
from asyncticket.seats.infrastructure.repositories import (
    SqlAlchemyPerformanceSeatRepository,
    SqlAlchemySeatInfoRepository,
)


# 1) 라우터가 요청할 주입 지점
def provide_performance_seat_service() -> PerformanceSeatService:
    raise RuntimeError("좌석 조회 서비스 연결이 필요합니다.")


# 2) 조회·예매 연결·해제에 쓸 동일 세션 서비스 구성
def create_performance_seat_service(
    session: AsyncSession, *, seat_list_cache: SeatListCache | None = None
) -> PerformanceSeatService:
    return PerformanceSeatService(
        SqlAlchemyPerformanceSeatRepository(session),
        SqlAlchemySeatInfoRepository(session),
        seat_list_cache=seat_list_cache,
    )


async def provide_seat_list_cache() -> AsyncIterator[SeatListCache | None]:
    # 좌석 요청에서만 연결하고 종료한다. 공용 DB 수명주기는 변경하지 않는다.
    url = os.getenv("SEAT_CACHE_REDIS_URL", "")
    if not url:
        yield None
        return
    try:
        client = Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=0.15,
            socket_timeout=0.15,
            retry=Retry(NoBackoff(), 0),
        )
    except ValueError:
        logging.getLogger(__name__).warning("좌석 Redis 설정 오류, 캐시 비활성화")
        yield None
        return
    try:
        yield RedisSeatListCache(client)
    finally:
        try:
            await client.aclose()
        except (RedisError, OSError):
            logging.getLogger(__name__).warning("좌석 Redis 연결 종료 실패")


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
        cache: Annotated[SeatListCache | None, Depends(provide_seat_list_cache)],
    ) -> PerformanceSeatService:
        return create_performance_seat_service(session, seat_list_cache=cache)

    app.dependency_overrides[provide_performance_seat_service] = (
        performance_seat_service
    )
