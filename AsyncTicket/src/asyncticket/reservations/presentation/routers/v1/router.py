"""
<예매 endpoint 정보>

- 예매 생성 : POST /v1/reservations
- 예매 목록 조회 : GET /v1/reservations
- 예매 상세 조회 : GET /v1/reservations/{reserv_id}
- 예매 취소 : POST /v1/reservations/{reserv_id}/cancel

- 예매자는 요청 본문이 아니라 로그인 토큰(get_current_user)에서만 가져온다
- 결제 후 확정(confirm)은 결제 흐름에서 호출하므로 여기에는 없다
"""

from typing import Annotated


# 라우터 작업 초기세팅
from fastapi import (
    APIRouter, # 라우터 객체 만들기 
    status,    # status.HTTP_201_CREATED 같은 상태 코드 이름
    Path,      # 주소 안의 값({reserv_id}) 검사
    Depends    # 의존성 주입
    )

from asyncticket.auth.presentation.dependencies import get_current_user
from asyncticket.users.domain.users import User
from asyncticket.shared.core.schemas import APIResponse

from asyncticket.reservations.application.service import ReservationService
from asyncticket.reservations.presentation.schemas import ReservationCreateRequest, ReservationResponse
from asyncticket.wiring.reservations import provide_reservation_service


router = APIRouter(prefix="/v1/reservations", tags=["예매"])


# 라우터마다 반복되는 의존성 타입
CurrentUser = Annotated[User, Depends(get_current_user)]
Service = Annotated[ReservationService, Depends(provide_reservation_service)]


# 엔드포인트(endpoint) 정의

# 1) 예매생성
@router.post("",
    response_model=APIResponse[ReservationResponse],
    status_code=status.HTTP_201_CREATED,
    summary="예매 생성",
    description="로그인한 회원이 좌석 1개를 선택하면 예매대기(PENDING)로 생성되고 좌석이 선점되고, 결제 성공 후 확정")

async def create_reservation(
    request : ReservationCreateRequest,  # 요청 JSON (스키마가 검사)
    current_user : CurrentUser,          # 로그인 회원 (토큰에서)
    service : Service,                   # 예매 서비스 (wiring이 조립)
) -> APIResponse[ReservationResponse]:

    # 서비스 호출 : 예매자는 토큰의 회원, 회차/좌석은 요청 JSON에서
    reservation = await service.reserve(
        ticketholder_id = current_user.user_id,
        perf_id = request.perf_id,
        perf_seat_id = request.perf_seat_id
    )

    # from_entity(엔티티 → 응답 스키마) → APIResponse.ok(팀 공통 형식)
    return APIResponse.ok(
        data=ReservationResponse.from_entity(reservation),
        message="예매가 생성되었습니다. 결제를 진행해 주세요.",
        code="RESERVATION_CREATED"
    )


# 2) 예매 목록 조회
@router.get("",
    response_model=APIResponse[list[ReservationResponse]],
    summary="예매 목록 조회",
    description="로그인한 회원이 본인의 예매 내역을 최신순으로 확인합니다. 취소한 예매도 포함합니다.")

async def get_list_reservation(
    current_user : CurrentUser,
    service : Service,
) -> APIResponse[list[ReservationResponse]]:

    reservations = await service.list_reservations(ticketholder_id=current_user.user_id)

    return APIResponse.ok(
        data=[ReservationResponse.from_entity(r) for r in reservations],
        message="예매 목록 조회가 완료되었습니다",
        code="RESERVATIONS_FOUND"
    )


# 3) 예매 상세 조회  
@router.get("/{reserv_id}",
    response_model=APIResponse[ReservationResponse],
    summary="예매 상세 조회",
    description="로그인한 회원이 본인의 예매 1건을 공연·좌석·결제 정보까지 자세히 확인")

async def get_detail_reservation(
    current_user : CurrentUser,
    service : Service,
    reserv_id: int = Path(gt=0, description="예매번호")
) -> APIResponse[ReservationResponse]:

    reservation = await service.get_reservation(
        reserv_id=reserv_id,
        ticketholder_id=current_user.user_id
    )

    return APIResponse.ok(
        data=ReservationResponse.from_entity(reservation),
        message="예매 상세 조회가 완료되었습니다",
        code="RESERVATION_DETAIL_FOUND"
    )


# 4) 예매 취소
@router.post("/{reserv_id}/cancel",
    response_model=APIResponse[ReservationResponse],
    summary="예매 취소",
    description="로그인한 회원이 본인의 확정된 예매를 공연 시작 전까지 취소하면 좌석이 다시 판매 가능해집니다.")

async def cancel_reservation(
    current_user : CurrentUser,
    service : Service,
    reserv_id: int = Path(gt=0, description="예매번호")
) -> APIResponse[ReservationResponse] :

    reservation = await service.cancel(
        reserv_id=reserv_id,
        ticketholder_id=current_user.user_id
    )

    return APIResponse.ok(
        data=ReservationResponse.from_entity(reservation),
        message="예매가 취소되었습니다",
        code="RESERVATION_CANCELED"
    )

