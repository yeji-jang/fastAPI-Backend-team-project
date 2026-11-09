from asyncticket.auth.domain.entities import BlacklistedToken
from asyncticket.auth.domain.exceptions import InvalidAccessTokenError
from asyncticket.auth.domain.repository import TokenBlacklistRepository
from asyncticket.auth.domain.service import (
    AccessTokenPayload,
    TokenProvider,
)
from asyncticket.shared.core.exceptions import (
    UnauthorizedException,
)
from asyncticket.users.domain.repository import UserRepository
from asyncticket.users.domain.service import PasswordHasher
from asyncticket.users.domain.users import User


class AuthApplicationService:
    def __init__(
        self,
        user_repository: UserRepository,
        token_blacklist_repository: TokenBlacklistRepository,
        token_provider: TokenProvider,
        password_hasher: PasswordHasher,
    ) -> None:
        self.user_repository = user_repository
        self.token_blacklist_repository = token_blacklist_repository
        self.token_provider = token_provider
        self.password_hasher = password_hasher

    async def login(
        self,
        email: str,
        password: str,
    ) -> tuple[User, AccessTokenPayload]:
        """
        이메일과 비밀번호로 로그인한다.

        처리 순서:
        1. 이메일로 회원 조회
        2. 회원 탈퇴 여부 확인
        3. 비밀번호 검증
        4. Access Token 발급
        """

        user = await self.user_repository.find_by_email(
            email.strip().lower()
        )

        # 이메일 존재 여부와 비밀번호 오류를 같은 응답으로 처리한다.
        # 공격자가 특정 이메일의 가입 여부를 알아내지 못하게 하기 위함이다.
        if user is None:
            raise UnauthorizedException(
                message="이메일 또는 비밀번호가 올바르지 않습니다.",
                error_code="INVALID_LOGIN_CREDENTIALS",
            )

        if user.is_withdrawn:
            raise UnauthorizedException(
                message="탈퇴한 회원은 로그인할 수 없습니다.",
                error_code="USER_ALREADY_WITHDRAWN",
            )

        password_matches = self.password_hasher.verify(
            raw_password=password,
            hashed_password=user.password_hash,
        )

        if not password_matches:
            raise UnauthorizedException(
                message="이메일 또는 비밀번호가 올바르지 않습니다.",
                error_code="INVALID_LOGIN_CREDENTIALS",
            )

        if user.user_id is None:
            raise UnauthorizedException(
                message="회원 식별 정보가 올바르지 않습니다.",
                error_code="INVALID_USER_ID",
            )

        token_payload = self.token_provider.issue_access_token(
            user_id=user.user_id,
            role=user.role,
        )

        return user, token_payload

    async def authenticate(
        self,
        access_token: str,
    ) -> User:
        """
        Access Token을 검증하고 현재 회원을 반환한다.

        처리 순서:
        1. JWT 서명·만료 검증
        2. 블랙리스트 여부 확인
        3. 토큰의 user_id로 회원 조회
        4. 탈퇴 회원 여부 확인
        """

        payload = await self._get_valid_payload(access_token)

        user = await self.user_repository.find_by_id(
            payload.user_id
        )

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

    async def logout(self, access_token: str) -> None:
        """
        Access Token을 블랙리스트에 등록한다.

        로그아웃하더라도 이미 발급된 JWT 자체를 수정할 수는 없으므로
        jti를 blacklist 테이블에 저장하여 이후 인증을 차단한다.
        """

        payload = await self._get_verified_payload(access_token)

        blacklisted_token = BlacklistedToken(
            jti_token=payload.jti,
            expired_at=payload.expires_at,
        )

        await self.token_blacklist_repository.save(
            blacklisted_token
        )

    async def get_authenticated_payload(
        self,
        access_token: str,
    ) -> AccessTokenPayload:
        """
        현재 토큰의 검증된 payload를 반환한다.

        이 메서드는 이후 관리자 권한 검사나
        토큰 기반 사용자 식별이 필요할 때 사용할 수 있다.
        """

        return await self._get_valid_payload(access_token)

    async def _get_verified_payload(
        self,
        access_token: str,
    ) -> AccessTokenPayload:
        try:
            return self.token_provider.verify_access_token(
                access_token
            )
        except (InvalidAccessTokenError, ValueError, TypeError) as exc:
            raise UnauthorizedException(
                message="인증 정보가 올바르지 않거나 만료되었습니다.",
                error_code="INVALID_ACCESS_TOKEN",
            ) from exc

    async def _get_valid_payload(
        self,
        access_token: str,
    ) -> AccessTokenPayload:
        payload = await self._get_verified_payload(access_token)

        is_blacklisted = await self.token_blacklist_repository.exists(
            payload.jti
        )

        if is_blacklisted:
            raise UnauthorizedException(
                message="폐기된 인증 정보입니다.",
                error_code="REVOKED_ACCESS_TOKEN",
            )

        return payload
