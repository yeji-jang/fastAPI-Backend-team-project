"""요청 단위의 공통 인증 서비스를 공연·회차 사용자 계약에 연결한다."""
from typing import Annotated

from fastapi import Depends, FastAPI, Request

from asyncticket.auth.application.service import AuthApplicationService
from asyncticket.auth.domain.repository import TokenBlacklistRepository
from asyncticket.shared.core.exceptions import UnauthorizedException
from asyncticket.shared.domain.catalog import (
    AuthenticationRequiredError, CatalogActor, CatalogAuthenticator, CatalogIntegrationError,
)
from asyncticket.shared.presentation.catalog_auth import provide_catalog_authenticator
from asyncticket.users.domain.repository import UserRepository
from asyncticket.users.domain.service import PasswordHasher
from asyncticket.wiring.auth import get_blacklist_repository, get_token_provider
from asyncticket.wiring.users import get_password_hasher, get_user_repository


class AuthServiceCatalogAuthenticator:
    def __init__(self, users: UserRepository, blacklist: TokenBlacklistRepository,
                 hasher: PasswordHasher) -> None:
        self.users = users
        self.blacklist = blacklist
        self.hasher = hasher

    async def authenticate(self, token: str) -> CatalogActor:
        # 지연 생성하여 공개 조회·문서·토큰 없는 요청에 JWT 설정을 요구하지 않는다.
        try:
            provider = get_token_provider()
        except (RuntimeError, ValueError) as exc:
            raise CatalogIntegrationError("공통 인증 설정이 필요합니다.") from exc
        service = AuthApplicationService(self.users, self.blacklist, provider, self.hasher)
        try:
            user = await service.authenticate(token)
        except UnauthorizedException as exc:
            # 공연·회차의 공통 401 응답 및 WWW-Authenticate 계약을 유지한다.
            raise AuthenticationRequiredError("인증 정보가 없거나 만료되었습니다.") from exc
        # JWT role claim 대신 DB에서 확인한 현재 사용자 권한을 사용한다.
        return CatalogActor(user_id=user.user_id, role=user.role.value)


def create_catalog_authenticator(
    request: Request,
    users: Annotated[UserRepository, Depends(get_user_repository)],
    blacklist: Annotated[TokenBlacklistRepository, Depends(get_blacklist_repository)],
    hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
) -> CatalogAuthenticator:
    configured = request.app.state.catalog_authenticator
    if configured is not None:
        return configured
    return AuthServiceCatalogAuthenticator(users, blacklist, hasher)


def wire_dependencies(app: FastAPI) -> None:
    app.dependency_overrides[provide_catalog_authenticator] = create_catalog_authenticator
