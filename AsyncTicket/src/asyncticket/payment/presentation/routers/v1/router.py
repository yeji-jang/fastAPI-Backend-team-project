"""
결제 API
    POST /v1/payments                        결제 시작 (본문: reserv_id만)
    POST /v1/payments/approve                결제 승인 (토스 결제창 성공 후)
    GET  /v1/reservations/{reserv_id}/payment 예매의 결제 조회
    - 결제 취소(환불)는 공개 API가 없다. 예매 취소가 PaymentService.refund_for_reservation을 내부 호출한다.
    - 예매 URL 아래 경로는 좌석의 /reservations/{reserv_id}/seats와 같은 방식으로 결제 라우터에 둔다.

<프론트 흐름>
    1) 예매하기(예매 API) → 예매대기
    2) POST /v1/payments                → order_id·amount를 받아 토스 결제창을 연다
    3) 토스 결제창 성공 → 성공 URL로 paymentKey·orderId·amount를 받는다
    4) POST /v1/payments/approve        → 결제완료 + 예매확정
    5) GET /v1/reservations/{id}/payment → 결제 상태 확인

<공통>
    - 모든 결제 API는 로그인이 필요하고, 본인 예매만 다룬다 (본인 확인은 예매가 판단)
    - 성공 응답은 팀 규칙대로 APIResponse.ok로 감싼다
"""

from typing import Annotated

# <FastAPI>
from fastapi import APIRouter, Depends, Path, Response, status

# <인증 - 로그인 회원>
from asyncticket.auth.presentation.dependencies import get_current_user # 토큰 → 회원
from asyncticket.users.domain.users import User # 회원 엔티티

# <결제>
from asyncticket.payment.application.service import PaymentService # 결제 응용 서비스
from asyncticket.payment.presentation.dependencies import provider_payment_service # 서비스 주입 지점 (wiring이 교체)
from asyncticket.payment.presentation.schemas import (
    PaymentApproveRequest,  # 승인 요청
    PaymentResponse,        # 결제 응답
    PaymentStartRequest,    # 시작 요청
)

# <Shared - 팀 공통 응답>
from asyncticket.shared.core.schemas import APIResponse

router = APIRouter(prefix="/v1", tags=["결제"])

# 의존성 별칭 (예매 라우터와 같은 방식)
CurrentUser = Annotated[User, Depends(get_current_user)]                    # 로그인 회원
Service = Annotated[PaymentService, Depends(provider_payment_service)]     # 결제 서비스


# 엔드포인트(endpoint) 정의

# 1. 결제 시작
@router.post(
    "/payments",
    status_code=status.HTTP_201_CREATED,
    response_model=APIResponse[PaymentResponse],
    summary="결제 시작",
    description="본인의 예매대기 건으로 결제(READY)를 만들고 토스 결제창에 쓸 order_id와 금액을 준다. "
    "이미 결제대기면 같은 결제를 200으로 돌려주고, 처리된 결제가 있으면 다시 시작할 수 없다(409).",
)
async def start_payment(
    body: PaymentStartRequest,
    current_user: CurrentUser,
    service: Service,
    response: Response,
) -> APIResponse[PaymentResponse]:
    # 1) 결제 시작 (새로 만들었으면 201, 진행 중인 결제를 돌려주면 200)
    payment, created = await service.start(reserv_id=body.reserv_id, ticketholder_id=current_user.user_id)
    if not created:
        response.status_code = status.HTTP_200_OK
    # 2) 조회 주소를 Location으로 알려 준다 (팀 규칙: 201과 Location 유지)
    response.headers["Location"] = f"/v1/reservations/{payment.reserv_id}/payment"
    return APIResponse.ok(
        data=PaymentResponse.from_entity(payment, service.order_id_of(payment)),
        message="결제를 시작했습니다" if created else "진행 중인 결제가 있습니다",
        code="PAYMENT_READY",
    )


# 2. 결제 승인
@router.post(
    "/payments/approve",
    response_model=APIResponse[PaymentResponse],
    summary="결제 승인",
    description="토스 결제창 성공 후 받은 paymentKey·orderId·amount로 승인한다. 금액이 다르면 토스를 호출하지 않는다.",
)
async def approve_payment(
    body: PaymentApproveRequest,
    current_user: CurrentUser,
    service: Service,
) -> APIResponse[PaymentResponse]:
    payment = await service.approve(
        payment_key=body.payment_key,
        order_id=body.order_id,
        amount=body.amount,
        ticketholder_id=current_user.user_id,
    )
    return APIResponse.ok(
        data=PaymentResponse.from_entity(payment, body.order_id),
        message="결제가 승인되었습니다",
        code="PAYMENT_APPROVED",
    )


# 3. 예매의 결제 조회
@router.get(
    "/reservations/{reserv_id}/payment",
    response_model=APIResponse[PaymentResponse],
    summary="예매의 결제 조회",
    description="본인 예매의 결제를 조회한다.",
)
async def get_reservation_payment(
    current_user: CurrentUser,
    service: Service,
    reserv_id: int = Path(gt=0, description="예매 ID"),
) -> APIResponse[PaymentResponse]:
    payment = await service.get_for_reservation(reserv_id=reserv_id, ticketholder_id=current_user.user_id)
    return APIResponse.ok(data=PaymentResponse.from_entity(payment, service.order_id_of(payment)))
