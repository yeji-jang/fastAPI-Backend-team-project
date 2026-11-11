"""표현 계층: 공연 API 5개의 HTTP 입력·출력을 담당한다."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from fastapi_cache.decorator import cache

from asyncticket.shared.presentation.catalog_auth import get_current_catalog_actor
from asyncticket.wiring.shows import provide_show_service
from asyncticket.shared.domain.catalog import CatalogActor
from asyncticket.shared.core.schemas import APIResponse
from asyncticket.shows.application.service import ShowApplicationService
from asyncticket.shows.domain.show import ShowQuery
from asyncticket.shows.presentation.schemas import (
    ShowCreateRequest, ShowListResponse, ShowResponse, ShowUpdateRequest,
)

ERROR_RESPONSES = {code: {"model": APIResponse[None]} for code in (401, 403, 404, 409, 422, 500, 503)}
router = APIRouter(prefix="/v1/shows", tags=["공연"], responses=ERROR_RESPONSES)
ShowService = Annotated[ShowApplicationService, Depends(provide_show_service)]
Actor = Annotated[CatalogActor, Depends(get_current_catalog_actor)]
ShowId = Annotated[int, Path(gt=0, le=9223372036854775807, description="공연 ID")]


@cache(expire=30, namespace="shows")
async def _cached_show_list(
    *, query: ShowQuery, service: ShowApplicationService,
    cache_scope: str, cache_generation: int,
) -> ShowListResponse:
    # 요청별 envelope 대신 공개 data만 저장한다.
    items, total = await service.find_all(query)
    return ShowListResponse(
        items=[ShowResponse.model_validate(item) for item in items],
        page=query.page, size=query.size, total=total,
    )


@cache(expire=60, namespace="shows")
async def _cached_show_detail(
    *, show_id: int, service: ShowApplicationService,
    cache_scope: str, cache_generation: int,
) -> ShowResponse:
    return ShowResponse.model_validate(await service.find_by_id(show_id))


@router.get("", response_model=APIResponse[ShowListResponse], summary="공연 목록 조회")
async def get_list_show(
    request: Request, service: ShowService,
    page: Annotated[int, Query(ge=1, le=2147483647, description="페이지")] = 1,
    size: Annotated[int, Query(ge=1, le=100, description="페이지 크기")] = 20,
    keyword: Annotated[str | None, Query(max_length=255, description="공연명 검색")] = None,
    type: Annotated[str | None, Query(max_length=50, description="공연 분류")] = None,
    venues_id: Annotated[int | None, Query(gt=0, le=9223372036854775807, description="공연장 ID")] = None,
) -> APIResponse[ShowListResponse]:
    query = ShowQuery(page, size, keyword, type, venues_id)
    if getattr(request.app.state, "catalog_cache_enabled", False):
        data = await _cached_show_list(
            query=query, service=service,
            cache_scope=request.app.state.catalog_cache_scope,
            cache_generation=request.app.state.catalog_cache_generations["shows"],
        )
    else:
        items, total = await service.find_all(query)
        data = ShowListResponse(
            items=[ShowResponse.model_validate(item) for item in items],
            page=page, size=size, total=total,
        )
    return APIResponse[ShowListResponse].ok(data=data)


@router.get("/{show_id}", response_model=APIResponse[ShowResponse], summary="공연 상세 조회")
async def get_detail_show(
    show_id: ShowId, request: Request, service: ShowService,
) -> APIResponse[ShowResponse]:
    if getattr(request.app.state, "catalog_cache_enabled", False):
        data = await _cached_show_detail(
            show_id=show_id, service=service,
            cache_scope=request.app.state.catalog_cache_scope,
            cache_generation=request.app.state.catalog_cache_generations["shows"],
        )
    else:
        data = ShowResponse.model_validate(await service.find_by_id(show_id))
    return APIResponse[ShowResponse].ok(data=data)


@router.post("", status_code=201, response_model=APIResponse[ShowResponse], summary="공연 등록")
async def create_show(
    body: ShowCreateRequest, request: Request, response: Response, actor: Actor, service: ShowService,
) -> APIResponse[ShowResponse]:
    # 라우터는 SQL을 실행하지 않고 스키마를 서비스 입력으로 바꾼다.
    show = await service.create(body.model_dump(), actor)
    if getattr(request.app.state, "catalog_cache_enabled", False):
        await request.app.state.invalidate_catalog_cache("shows")
    response.headers["Location"] = f"/v1/shows/{show.show_id}"
    return APIResponse[ShowResponse].ok(data=ShowResponse.model_validate(show))


@router.patch("/{show_id}", response_model=APIResponse[ShowResponse], summary="공연 수정")
async def update_show(
    show_id: ShowId, body: ShowUpdateRequest, request: Request, actor: Actor, service: ShowService,
) -> APIResponse[ShowResponse]:
    # exclude_unset 덕분에 '생략'과 'null로 비우기'를 구분할 수 있다.
    show = await service.update(show_id, body.model_dump(exclude_unset=True), actor)
    if getattr(request.app.state, "catalog_cache_enabled", False):
        await request.app.state.invalidate_catalog_cache("shows")
    return APIResponse[ShowResponse].ok(data=ShowResponse.model_validate(show))


@router.delete("/{show_id}", status_code=204, response_class=Response, summary="공연 삭제")
async def delete_show(
    show_id: ShowId, request: Request, actor: Actor, service: ShowService,
) -> Response:
    await service.delete(show_id, actor)
    if getattr(request.app.state, "catalog_cache_enabled", False):
        await request.app.state.invalidate_catalog_cache("shows", "performances")
    return Response(status_code=204)
