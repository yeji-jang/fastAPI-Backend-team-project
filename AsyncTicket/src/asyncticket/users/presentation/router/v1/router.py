from typing import Annotated

from fastapi import APIRouter, Depends, status

from asyncticket.users.presentation.dependencies import (
    get_current_user,
    get_user_service,
)
from asyncticket.shared.core.schemas import APIResponse
from asyncticket.users.application.service import (
    UserApplicationService,
)
from asyncticket.users.domain.users import User
from asyncticket.users.presentation.schema import (
    ChangePasswordRequest,
    SignUpRequest,
    UserResponse,
)


router = APIRouter(
    prefix="/v1/users",
    tags=["Users"],
)


@router.post(
    "",
    response_model=APIResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
    summary="회원가입",
)
async def register_user(
    request: SignUpRequest,
    user_service: Annotated[
        UserApplicationService,
        Depends(get_user_service),
    ],
) -> APIResponse[UserResponse]:
    user = await user_service.register_user(
        email=str(request.email),
        name=request.name,
        password=request.password,
        phone_number=request.phone_number,
        birth=request.birth,
        address=request.address,
        address_detail=request.address_detail,
        post_no=request.post_no,
    )

    response_data = UserResponse.model_validate(user)

    return APIResponse.ok(
        data=response_data,
        message="회원가입이 완료되었습니다.",
        code="USER_REGISTERED",
    )


@router.get(
    "/me",
    response_model=APIResponse[UserResponse],
    status_code=status.HTTP_200_OK,
    summary="내 회원정보 조회",
)
async def get_my_profile(
    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],
) -> APIResponse[UserResponse]:
    response_data = UserResponse.model_validate(
        current_user
    )

    return APIResponse.ok(
        data=response_data,
        message="회원정보 조회가 완료되었습니다.",
        code="USER_FOUND",
    )


@router.patch(
    "/me/password",
    response_model=APIResponse[None],
    status_code=status.HTTP_200_OK,
    summary="비밀번호 변경",
)
async def change_my_password(
    request: ChangePasswordRequest,
    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],
    user_service: Annotated[
        UserApplicationService,
        Depends(get_user_service),
    ],
) -> APIResponse[None]:
    await user_service.change_password(
        user_id=current_user.user_id,
        old_password=request.old_password,
        new_password=request.new_password,
    )

    return APIResponse.ok(
        message="비밀번호가 변경되었습니다.",
        code="PASSWORD_CHANGED",
    )


@router.delete(
    "/me",
    response_model=APIResponse[None],
    status_code=status.HTTP_200_OK,
    summary="회원 탈퇴",
)
async def withdraw_my_account(
    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],
    user_service: Annotated[
        UserApplicationService,
        Depends(get_user_service),
    ],
) -> APIResponse[None]:
    await user_service.withdraw_user(
        target_user_id=current_user.user_id,
        requester_user_id=current_user.user_id,
    )

    return APIResponse.ok(
        message="회원 탈퇴가 완료되었습니다.",
        code="USER_WITHDRAWN",
    )