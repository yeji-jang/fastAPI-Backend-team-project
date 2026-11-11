# FastAPI 앱 생성 + 라우터 등록 (팀 공용)

# 함수를 "시작 → yield → 종료" 구조의 컨텍스트 매니저로 만들어 주는 데코레이터
import asyncio
import hashlib
import json
from contextlib import asynccontextmanager, suppress
from functools import partial
from pathlib import Path
from uuid import uuid4
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from fastapi.staticfiles import StaticFiles

from asyncticket.web import router as web_router

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
from asyncticket.wiring.reservations import run_reservation_expiry

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


# 교안의 fastapi-cache2 인메모리 캐시. 원본 DB와 업무 판정은 기존 경로를 유지한다.
CATALOG_CACHE_PREFIX = "asyncticket:catalog:v1"
CATALOG_CACHE_NAMESPACES = ("shows", "performances")


def catalog_cache_key_builder(func, namespace: str = "", *, args=(), kwargs=None, **_) -> str:
    """요청마다 바뀌는 서비스 객체 대신 검증된 조회 조건으로 키를 만든다."""
    values = dict(kwargs or {})
    values.pop("service", None)
    scope = values.pop("cache_scope")
    generation = values.pop("cache_generation")
    query = json.dumps(jsonable_encoder(values), sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(query.encode("utf-8")).hexdigest()
    return f"{namespace}:{scope}:{generation}:{func.__module__}.{func.__name__}:{digest}"


def init_catalog_cache(app: FastAPI) -> None:
    """실제 서버 시작 시 프로세스 메모리 캐시를 준비한다. 외부 연결은 없다."""
    FastAPICache.init(
        InMemoryBackend(), prefix=CATALOG_CACHE_PREFIX,
        key_builder=catalog_cache_key_builder,
    )
    app.state.catalog_cache_enabled = True
    logger.info("공연·회차 인메모리 조회 캐시 활성화")


async def invalidate_catalog_cache(app: FastAPI, *namespaces: str) -> None:
    """DB commit 후 키 세대를 바꿔 이전 조회가 늦게 저장돼도 재사용하지 않는다."""
    if not app.state.catalog_cache_enabled:
        return
    for namespace in namespaces:
        app.state.catalog_cache_generations[namespace] += 1
        prefix = f"{FastAPICache.get_prefix()}:{namespace}:{app.state.catalog_cache_scope}:"
        try:
            await FastAPICache.get_backend().clear(namespace=prefix)
        except Exception:
            # 캐시 정리가 이미 성공한 DB 저장을 실패로 바꾸면 안 된다.
            logger.warning("조회 캐시 삭제 실패: namespace=%s", namespace, exc_info=True)


async def clear_catalog_cache(app: FastAPI) -> None:
    """종료하는 앱의 키만 정리한다. 같은 프로세스의 다른 앱 설정은 보존한다."""
    if not app.state.catalog_cache_enabled:
        return
    await invalidate_catalog_cache(app, *CATALOG_CACHE_NAMESPACES)
    app.state.catalog_cache_enabled = False


# 서버 시작/종료 시 실행할 작업 정의
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    expiry_task = None

    try:
        logger.info("애플리케이션 시작, 모델 초기화 및 DB 스키마 확인 중...")

        # 팀 공용 시작 절차는 앱 생성과 분리해 실제 서버 시작 시 실행한다.
        init_models()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        init_catalog_cache(app)
        logger.info("애플리케이션 준비 완료")
        expiry_task = asyncio.create_task(run_reservation_expiry())  # 예매 만료 작업 시작

        # ───────── 여기서 멈춰서 서버가 요청을 처리 ─────────
        yield
    finally:
        # 시작 실패 또는 요청 처리 중 예외가 있어도 DB 풀을 정리한다.
        logger.info("애플리케이션 종료 처리 중...")
        if expiry_task is not None:   # 예매 만료 작업 정리
            expiry_task.cancel() 
            with suppress(asyncio.CancelledError):     
                await expiry_task                        
        try:
            await clear_catalog_cache(app)
        finally:
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
    app.state.catalog_cache_enabled = False
    app.state.catalog_cache_scope = uuid4().hex
    app.state.catalog_cache_generations = {name: 0 for name in CATALOG_CACHE_NAMESPACES}
    app.state.invalidate_catalog_cache = partial(invalidate_catalog_cache, app)
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
    # 화면도 같은 주소의 팀 API를 호출한다.
    app.include_router(web_router)
    app.mount(
        "/venue-assets",
        StaticFiles(directory=Path(__file__).parent / "static" / "venue"),
        name="venue_assets",
    )
    return app


# uvicorn asyncticket.main:app 진입점을 유지한다.
app = create_app()
