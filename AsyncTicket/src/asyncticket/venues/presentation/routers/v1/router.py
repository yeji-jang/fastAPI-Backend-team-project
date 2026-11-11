from typing import Annotated
from fastapi import APIRouter, Depends, status, Query

from asyncticket.shared.core.schemas import APIResponse
from asyncticket.venues.presentation.schemas import (
    SearchVenuesRequest,
    CreateVenueRequest,
    UpdateVenueRequest,
    VenueResponse,
)
from asyncticket.venues.presentation.dependencies import (
    provider_venue_service,
    provider_venue_repository,
)
from asyncticket.venues.application.service import VenueService

router = APIRouter(prefix="/v1/venues", tags=["Venues"])


# TODO : APIResponse 추가시 반환 타입 변경하기
@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="공연장 단건 조회",
    description="venues_id로 공연장 단건 조회",
)
async def get_venue(
    venues_id: int,
    venue_service: Annotated[VenueService, Depends(provider_venue_service)],
) -> APIResponse[VenueResponse]:
    venue = await venue_service.get_venue(venues_id)

    return APIResponse[VenueResponse].ok(
        data=VenueResponse.model_validate(venue),
        message="공연장 조회에 성공했습니다.",
    )


@router.get(
    "/list",
    status_code=status.HTTP_200_OK,
    summary="공연장 다건 조회",
    description="name, address, page, page_size로 공연장 다건 조회",
)
async def get_venue(
    request: Annotated[SearchVenuesRequest, Query()],
    venue_service: Annotated[VenueService, Depends(provider_venue_service)],
) -> APIResponse[list[VenueResponse]]:
    venues = await venue_service.get_list_venue(
        request.name, request.address, request.page, request.page_size
    )

    return APIResponse[list[VenueResponse]].ok(
        data=[VenueResponse.model_validate(venue) for venue in venues],
        message="공연장 목록 조회에 성공하였습니다.",
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="공연장 생성",
    description="새로운 공연장을 등록합니다.",
)
async def create_venue(
    request: CreateVenueRequest,
    venue_service: Annotated[VenueService, Depends(provider_venue_service)],
) -> APIResponse[VenueResponse]:
    venue = await venue_service.create_venue(
        request.name, request.address, request.address_detail, request.post_no
    )
    return APIResponse[VenueResponse].ok(
        data=VenueResponse.model_validate(venue),
        message="공연장 저장에 성공하였습니다.",
    )


@router.patch(
    "",
    status_code=status.HTTP_200_OK,
    summary="공연장 수정",
    description="기존 공연장 정보를 수정합니다.",
)
async def update_venue(
    request: UpdateVenueRequest,
    venue_service: Annotated[VenueService, Depends(provider_venue_service)],
) -> APIResponse[VenueResponse]:
    changes = request.model_dump(
        exclude_unset=True,
        exclude={"venues_id"},
    )

    venue = await venue_service.update_venue(request.venues_id, changes)

    return APIResponse[VenueResponse].ok(
        data=VenueResponse.model_validate(venue),
        message="공연장 수정에 성공하였습니다.",
    )
