# FastAPI 앱 생성 + 라우터 등록 (팀 공용)

# 함수를 "시작 → yield → 종료" 구조의 컨텍스트 매니저로 만들어 주는 데코레이터
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from asyncticket.performances.presentation.router import router as performance_router
from asyncticket.reservations.presentation.routers.v1.router import router as reservation_router
from asyncticket.seats.presentation.router import router as seat_router
# engine: DB 연결(커넥션 풀) / close_db: 서버 종료 시 커넥션 풀 정리
from asyncticket.shared.core.database import close_db, engine
from asyncticket.shared.core.exception_handlers import register_exception_handlers
# 공용 로거 생성 함수
from asyncticket.shared.core.logger import get_logger
from asyncticket.shared.core.middlewares import CorsFastAPI
# Base : 모든 모델의 부모, 등록된 테이블 정보(metadata)를 가짐
# init_models : 모든 도메인 models.py를 import해서 Base에 테이블 등록
from asyncticket.shared.core.models import Base, init_models
from asyncticket.shared.domain.catalog import CatalogAuthenticator, CatalogPolicy
from asyncticket.shared.presentation.catalog_http import register_catalog_errors
from asyncticket.reservations.presentation.exception_handlers import register_reservation_errors
from asyncticket.shows.presentation.router import router as show_router
from asyncticket.wiring import wire_dependencies
from asyncticket.venues.presentation.routers.v1.router import router as venue_router

# auth_router, users_router는 FastAPI 앱에 등록할 라우터
from asyncticket.auth.presentation.routers.v1.router import (
    router as auth_router,
)
from asyncticket.users.presentation.router.v1.router import (
    router as users_router,
)
from asyncticket.payment.presentation.routers.v1.router import router as payment_router

# 이 파일에서 사용할 로거 (로그에 "app.main"이라는 이름으로 표시됨)
logger = get_logger("app.main")


# 서버 시작/종료 시 실행할 작업 정의
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        logger.info("애플리케이션 시작, 모델 초기화 및 DB 스키마 확인 중...")

        # 팀 공용 시작 절차는 앱 생성과 분리해 실제 서버 시작 시 실행한다.
        init_models()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info("애플리케이션 준비 완료")
        # ───────── 여기서 멈춰서 서버가 요청을 처리 ─────────
        yield
    finally:
        # 시작 실패 또는 요청 처리 중 예외가 있어도 DB 풀을 정리한다.
        logger.info("애플리케이션 종료 처리 중...")
        await close_db()


def create_app(
    authenticator: CatalogAuthenticator | None = None,
    policy: CatalogPolicy | None = None,
) -> FastAPI:
    """공용 수명주기와 공연·회차 API의 설정·라우터를 한 앱에 조립한다."""
    app = CorsFastAPI(
        title="AsyncTicket API",
        description="공연 티켓 예매 백엔드 API",
        version="1.0.0",
        lifespan=lifespan,
    )
    # 앱마다 설정을 분리한다. 인증기 미지정 시 wiring에서 공통 JWT 인증을 연결한다.
    app.state.catalog_authenticator = authenticator
    app.state.catalog_policy = policy if policy is not None else CatalogPolicy()
    register_exception_handlers(app)
    register_catalog_errors(app)
    register_reservation_errors(app)
    wire_dependencies(app)
    # 각 라우터에 /v1 prefix가 있으므로 앱에서 중복으로 붙이지 않는다.
    app.include_router(show_router)
    app.include_router(performance_router)


    app.include_router(venue_router)
    app.include_router(reservation_router)

    # 인증/사용자 관련 라우터를 등록한다.
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(seat_router)
    # 결제 관련 라우터
    app.include_router(payment_router)
    return app


# uvicorn asyncticket.main:app 진입점을 유지한다.
app = create_app()
