"""표현 계층: 공연회차 API 5개의 HTTP 입력·출력을 담당한다."""

from datetime import date as Date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from fastapi_cache.decorator import cache

from asyncticket.shared.presentation.catalog_auth import get_current_catalog_actor
from asyncticket.wiring.performances import provide_performance_service
from asyncticket.performances.application.service import (
    PERFORMANCE_DATE_MAX, PERFORMANCE_DATE_MIN, PerformanceApplicationService,
)
from asyncticket.performances.presentation.schemas import (
    PerformanceCreateRequest, PerformanceListResponse, PerformanceResponse,
    PerformanceUpdateRequest,
)
from asyncticket.shared.domain.catalog import CatalogActor
from asyncticket.shared.presentation.catalog_schemas import IsoDate
from asyncticket.shared.core.schemas import APIResponse

ERROR_RESPONSES = {code: {"model": APIResponse[None]} for code in (401, 403, 404, 409, 422, 500, 503)}
router = APIRouter(prefix="/v1", tags=["공연 회차"], responses=ERROR_RESPONSES)
PerformanceService = Annotated[PerformanceApplicationService, Depends(provide_performance_service)]
Actor = Annotated[CatalogActor, Depends(get_current_catalog_actor)]
ShowId = Annotated[int, Path(gt=0, le=9223372036854775807, description="공연 ID")]
PerformanceId = Annotated[int, Path(gt=0, le=9223372036854775807, description="공연 회차 ID")]


@cache(expire=10, namespace="performances")
async def _cached_performance_list(
    *, show_id: int, on_date: Date | None, service: PerformanceApplicationService,
    cache_scope: str, cache_generation: int,
) -> PerformanceListResponse:
    items = await service.find_all(show_id, on_date)
    return PerformanceListResponse(items=[PerformanceResponse.model_validate(item) for item in items])


@cache(expire=10, namespace="performances")
async def _cached_performance_detail(
    *, perf_id: int, service: PerformanceApplicationService,
    cache_scope: str, cache_generation: int,
) -> PerformanceResponse:
    return PerformanceResponse.model_validate(await service.find_by_id(perf_id))


@router.get(
    "/shows/{show_id}/performances", response_model=APIResponse[PerformanceListResponse],
    summary="공연별 회차 목록 조회",
)
async def get_list_performance(
    show_id: ShowId, request: Request, service: PerformanceService,
    date: Annotated[IsoDate | None, Query(
        ge=PERFORMANCE_DATE_MIN, le=PERFORMANCE_DATE_MAX,
        description="공연 시작일 (YYYY-MM-DD, Asia/Seoul, 0001-01-02~9999-12-30)",
    )] = None,
) -> APIResponse[PerformanceListResponse]:
    if getattr(request.app.state, "catalog_cache_enabled", False):
        # 캐시가 있어도 삭제된 부모 공연에 빈 목록을 반환하지 않는다.
        await service.ensure_show_exists(show_id)
        data = await _cached_performance_list(
            show_id=show_id, on_date=date, service=service,
            cache_scope=request.app.state.catalog_cache_scope,
            cache_generation=request.app.state.catalog_cache_generations["performances"],
        )
    else:
        items = await service.find_all(show_id, date)
        data = PerformanceListResponse(items=[PerformanceResponse.model_validate(item) for item in items])
    return APIResponse[PerformanceListResponse].ok(data=data)


@router.get(
    "/performances/{perf_id}", response_model=APIResponse[PerformanceResponse], summary="회차 상세 조회",
)
async def get_detail_performance(
    perf_id: PerformanceId, request: Request, service: PerformanceService,
) -> APIResponse[PerformanceResponse]:
    if getattr(request.app.state, "catalog_cache_enabled", False):
        data = await _cached_performance_detail(
            perf_id=perf_id, service=service,
            cache_scope=request.app.state.catalog_cache_scope,
            cache_generation=request.app.state.catalog_cache_generations["performances"],
        )
    else:
        data = PerformanceResponse.model_validate(await service.find_by_id(perf_id))
    return APIResponse[PerformanceResponse].ok(data=data)


@router.post(
    "/shows/{show_id}/performances", status_code=201,
    response_model=APIResponse[PerformanceResponse], summary="회차 등록",
)
async def create_performance(
    show_id: ShowId, body: PerformanceCreateRequest, request: Request, response: Response,
    actor: Actor, service: PerformanceService,
) -> APIResponse[PerformanceResponse]:
    performance = await service.create(show_id, body.model_dump(), actor)
    if getattr(request.app.state, "catalog_cache_enabled", False):
        await request.app.state.invalidate_catalog_cache("performances")
    response.headers["Location"] = f"/v1/performances/{performance.perf_id}"
    return APIResponse[PerformanceResponse].ok(data=PerformanceResponse.model_validate(performance))


@router.patch(
    "/performances/{perf_id}", response_model=APIResponse[PerformanceResponse], summary="회차 수정",
)
async def update_performance(
    perf_id: PerformanceId, body: PerformanceUpdateRequest, request: Request,
    actor: Actor, service: PerformanceService,
) -> APIResponse[PerformanceResponse]:
    performance = await service.update(perf_id, body.model_dump(exclude_unset=True), actor)
    if getattr(request.app.state, "catalog_cache_enabled", False):
        await request.app.state.invalidate_catalog_cache("performances")
    return APIResponse[PerformanceResponse].ok(data=PerformanceResponse.model_validate(performance))


@router.delete(
    "/performances/{perf_id}", status_code=204, response_class=Response, summary="회차 삭제",
)
async def delete_performance(
    perf_id: PerformanceId, request: Request, actor: Actor, service: PerformanceService,
) -> Response:
    await service.delete(perf_id, actor)
    if getattr(request.app.state, "catalog_cache_enabled", False):
        await request.app.state.invalidate_catalog_cache("performances")
    return Response(status_code=204)
