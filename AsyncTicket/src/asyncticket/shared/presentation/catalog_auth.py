"""표현 계층의 인증 연결 지점: 토큰 검증은 공통 인증 담당 모듈에 맡긴다."""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from asyncticket.shared.domain.catalog import (
    AuthenticationRequiredError, CatalogActor, CatalogAuthenticator, CatalogIntegrationError,
)

bearer = HTTPBearer(auto_error=False)


def provide_catalog_authenticator(request: Request) -> CatalogAuthenticator | None:
    return request.app.state.catalog_authenticator


async def get_current_catalog_actor(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    authenticator: Annotated[CatalogAuthenticator | None, Depends(provide_catalog_authenticator)],
) -> CatalogActor:
    if credentials is None:
        raise AuthenticationRequiredError("로그인이 필요합니다.")
    if authenticator is None:
        # 인증 코드가 없다고 user_id 헤더나 서명 미검증 JWT를 신뢰하지 않는다.
        raise CatalogIntegrationError("공통 인증 모듈 연결이 필요합니다.")
    actor = await authenticator.authenticate(credentials.credentials)
    if (
        not isinstance(actor, CatalogActor)
        or type(actor.user_id) is not int
        or not 0 < actor.user_id <= 9223372036854775807
    ):
        raise AuthenticationRequiredError("인증 정보가 없거나 만료되었습니다.")
    return actor
