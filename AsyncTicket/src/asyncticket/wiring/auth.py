# Auth 도메인 의존성 조립
import os
from typing import Annotated

from fastapi import Depends
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from sqlalchemy.ext.asyncio import AsyncSession

from asyncticket.auth.application.service import (
    AuthApplicationService,
)
from asyncticket.auth.domain.repository import (
    TokenBlacklistRepository,
)
from asyncticket.auth.domain.service import (
    AuthAccountReader,
    PasswordVerifier,
    TokenProvider,
)
from asyncticket.auth.infrastructure.repositories import (
    SqlAlchemyTokenBlacklistRepository,
)
from asyncticket.auth.infrastructure.security import (
    JwtTokenProvider,
)
from asyncticket.shared.core.database import get_db
from asyncticket.shared.core.exceptions import (
    ForbiddenException,
    UnauthorizedException,
)
from asyncticket.users.domain.repository import UserRepository
from asyncticket.users.domain.service import PasswordHasher
from asyncticket.users.domain.users import User, UserRole
from asyncticket.users.infrastructure.services import SqlAlchemyAuthAccountReader
from asyncticket.wiring.users import (
    get_password_hasher,
    get_user_repository,
)


DatabaseSession = Annotated[
    AsyncSession,
    Depends(get_db),
]


bearer_scheme = HTTPBearer(
    auto_error=False,
)


def get_blacklist_repository(
    session: DatabaseSession,
) -> TokenBlacklistRepository:
    return SqlAlchemyTokenBlacklistRepository(session)


def get_token_provider() -> TokenProvider:
    return JwtTokenProvider(
        secret_key=os.getenv("JWT_SECRET_KEY"),
        access_token_minutes=int(
            os.getenv(
                "JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
                "30",
            )
        ),
    )


def get_auth_account_reader(
    session: DatabaseSession,
) -> AuthAccountReader:
    return SqlAlchemyAuthAccountReader(session)


def get_auth_service(
    account_reader: Annotated[
        AuthAccountReader,
        Depends(get_auth_account_reader),
    ],
    blacklist_repository: Annotated[
        TokenBlacklistRepository,
        Depends(get_blacklist_repository),
    ],
    provider: Annotated[
        TokenProvider,
        Depends(get_token_provider),
    ],
    verifier: Annotated[
        PasswordVerifier,
        Depends(get_password_hasher),
    ],
) -> AuthApplicationService:
    return AuthApplicationService(
        account_reader=account_reader,
        token_blacklist_repository=blacklist_repository,
        token_provider=provider,
        password_verifier=verifier,
    )


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    auth_service: Annotated[
        AuthApplicationService,
        Depends(get_auth_service),
    ],
    user_repository: Annotated[
        UserRepository,
        Depends(get_user_repository),
    ],
) -> User:
    if credentials is None:
        raise UnauthorizedException(
            message="로그인이 필요합니다.",
            error_code="AUTHENTICATION_REQUIRED",
        )

    payload = await auth_service.get_authenticated_payload(
        credentials.credentials
    )

    user = await user_repository.find_by_id(payload.user_id)
    if user is None:
        raise UnauthorizedException(
            message="존재하지 않는 회원입니다.",
            error_code="USER_NOT_FOUND",
        )
    if user.is_withdrawn:
        raise UnauthorizedException(
            message="탈퇴한 회원은 이용할 수 없습니다.",
            error_code="USER_ALREADY_WITHDRAWN",
        )
    return user


async def require_admin(
    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],
) -> User:
    if current_user.role != UserRole.ADMIN:
        raise ForbiddenException(
            message="관리자 권한이 필요합니다.",
            error_code="ADMIN_PERMISSION_DENIED",
        )

    return current_user
