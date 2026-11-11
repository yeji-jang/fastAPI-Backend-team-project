from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)

from asyncticket.auth.application.service import (
    AuthApplicationService,
)
from asyncticket.auth.presentation.schemas import (
    LoginRequest,
    LoginResponse,
)
from asyncticket.auth.presentation.dependencies import (
    get_auth_service,
)
from asyncticket.shared.core.schemas import APIResponse


router = APIRouter(
    prefix="/v1/auth",
    tags=["Auth"],
)


bearer_scheme = HTTPBearer(
    auto_error=False,
)


@router.post(
    "/login",
    response_model=APIResponse[LoginResponse],
    status_code=status.HTTP_200_OK,
    summary="로그인",
)
async def login(
    request: LoginRequest,
    auth_service: Annotated[
        AuthApplicationService,
        Depends(get_auth_service),
    ],
) -> APIResponse[LoginResponse]:
    user, token_payload = await auth_service.login(
        email=request.email,
        password=request.password,
    )

    response_data = LoginResponse(
        access_token=token_payload.access_token,
        token_type="bearer",
        expires_at=token_payload.expires_at.isoformat(),
        user_id=user.user_id,
    )

    return APIResponse.ok(
        data=response_data,
        message="로그인에 성공했습니다.",
        code="LOGIN_SUCCESS",
    )


@router.post(
    "/logout",
    response_model=APIResponse[None],
    status_code=status.HTTP_200_OK,
    summary="로그아웃",
)
async def logout(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    auth_service: Annotated[
        AuthApplicationService,
        Depends(get_auth_service),
    ],
) -> APIResponse[None]:
    if credentials is None:
        from asyncticket.shared.core.exceptions import (
            UnauthorizedException,
        )

        raise UnauthorizedException(
            message="로그인이 필요합니다.",
            error_code="AUTHENTICATION_REQUIRED",
        )

    await auth_service.logout(
        access_token=credentials.credentials,
    )

    return APIResponse.ok(
        message="로그아웃이 완료되었습니다.",
        code="LOGOUT_SUCCESS",
    )