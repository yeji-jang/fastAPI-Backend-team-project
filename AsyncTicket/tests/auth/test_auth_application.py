import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from asyncticket.auth.application.service import (
    AuthApplicationService,
)
from asyncticket.auth.domain.entities import (
    BlacklistedToken,
)
from asyncticket.auth.domain.service import (
    AccessTokenPayload,
    AuthAccount,
    AuthRole,
)
from asyncticket.auth.infrastructure.security import JwtTokenProvider
from asyncticket.shared.core.exceptions import (
    UnauthorizedException,
)
from asyncticket.users.domain.users import (
    User,
    UserRole,
)
from asyncticket.wiring.auth import get_current_user


class FakePasswordHasher:
    def hash(self, raw_password: str) -> str:
        return f"hashed:{raw_password}"

    def verify(
        self,
        raw_password: str,
        hashed_password: str,
    ) -> bool:
        return hashed_password == f"hashed:{raw_password}"


class FakeAuthAccountReader:
    def __init__(self, account: AuthAccount):
        self.account = account

    async def find_by_id(self, user_id: int):
        if self.account.user_id == user_id:
            return self.account

        return None

    async def find_by_email(self, email: str):
        if email == "test@example.com":
            return self.account

        return None

class FakeBlacklistRepository:
    def __init__(self):
        self.tokens = set()

    async def save(self, token: BlacklistedToken):
        self.tokens.add(token.jti_token)

    async def exists(self, jti_token: str) -> bool:
        return jti_token in self.tokens

    async def delete_expired(self, current_time):
        return None


class FakeTokenProvider:
    def __init__(self):
        self.payload = AccessTokenPayload(
            access_token="fake-token",
            user_id=1,
            role=AuthRole.BUYER,
            jti="fake-jti",
            expires_at=(
                datetime.now(timezone.utc)
                + timedelta(minutes=30)
            ),
        )

    def issue_access_token(
        self,
        user_id: int,
        role: UserRole,
    ) -> AccessTokenPayload:
        return self.payload

    def verify_access_token(
        self,
        token: str,
    ) -> AccessTokenPayload:
        if token != self.payload.access_token:
            raise ValueError("invalid token")

        return self.payload


class AuthApplicationTests(
    unittest.IsolatedAsyncioTestCase
):
    def setUp(self):
        self.user = User(
            user_id=1,
            email="test@example.com",
            name="테스트",
            password_hash="hashed:Password1!",
            role=UserRole.BUYER,
            phone_number="010-1234-5678",
        )

        self.account_reader = FakeAuthAccountReader(
            AuthAccount(
                user_id=self.user.user_id,
                role=AuthRole.BUYER,
                password_hash=self.user.password_hash,
                is_withdrawn=self.user.is_withdrawn,
            )
        )
        self.blacklist_repository = (
            FakeBlacklistRepository()
        )
        self.token_provider = FakeTokenProvider()
        self.password_hasher = FakePasswordHasher()

        self.service = AuthApplicationService(
            account_reader=self.account_reader,
            token_blacklist_repository=(
                self.blacklist_repository
            ),
            token_provider=self.token_provider,
            password_verifier=self.password_hasher,
        )

    async def test_login_success(self):
        user, token = await self.service.login(
            email="test@example.com",
            password="Password1!",
        )

        self.assertEqual(user.user_id, 1)
        self.assertEqual(
            token.access_token,
            "fake-token",
        )

    async def test_login_failure(self):
        with self.assertRaises(UnauthorizedException):
            await self.service.login(
                email="test@example.com",
                password="WrongPassword1!",
            )

    async def test_logout_blacklists_token(self):
        await self.service.logout("fake-token")

        result = await (
            self.blacklist_repository.exists("fake-jti")
        )

        self.assertTrue(result)

    async def test_blacklisted_token_cannot_authenticate(self):
        await self.service.logout("fake-token")

        with self.assertRaises(UnauthorizedException):
            await self.service.authenticate("fake-token")

    async def test_logout_same_token_twice_is_idempotent(self):
        await self.service.logout("fake-token")
        await self.service.logout("fake-token")

        self.assertEqual(
            self.blacklist_repository.tokens,
            {"fake-jti"},
        )

    async def test_expired_token_cannot_authenticate(self):
        token_provider = JwtTokenProvider(
            secret_key="test-secret-key-for-auth-tests-32",
            access_token_minutes=-1,
        )
        token_payload = token_provider.issue_access_token(
            user_id=1,
            role=UserRole.BUYER,
        )
        service = AuthApplicationService(
            account_reader=self.account_reader,
            token_blacklist_repository=self.blacklist_repository,
            token_provider=token_provider,
            password_verifier=self.password_hasher,
        )

        with self.assertRaises(UnauthorizedException):
            await service.authenticate(token_payload.access_token)

    async def test_tampered_token_cannot_authenticate(self):
        token_provider = JwtTokenProvider(
            secret_key="test-secret-key-for-auth-tests-32",
        )
        token_payload = token_provider.issue_access_token(
            user_id=1,
            role=UserRole.BUYER,
        )
        tampered_token = (
            token_payload.access_token[:-1]
            + ("a" if token_payload.access_token[-1] != "a" else "b")
        )
        service = AuthApplicationService(
            account_reader=self.account_reader,
            token_blacklist_repository=self.blacklist_repository,
            token_provider=token_provider,
            password_verifier=self.password_hasher,
        )

        with self.assertRaises(UnauthorizedException):
            await service.authenticate(tampered_token)

    async def test_current_user_reads_user_once_and_rejects_withdrawn_user(self):
        auth_service = SimpleNamespace(
            get_authenticated_payload=AsyncMock(
                return_value=self.token_provider.payload,
            ),
        )
        user_repository = SimpleNamespace(
            find_by_id=AsyncMock(return_value=self.user),
        )
        credentials = SimpleNamespace(credentials="fake-token")

        result = await get_current_user(
            credentials,
            auth_service,
            user_repository,
        )

        self.assertIs(result, self.user)
        auth_service.get_authenticated_payload.assert_awaited_once_with(
            "fake-token"
        )
        user_repository.find_by_id.assert_awaited_once_with(1)

        self.user.deleted_at = datetime.now(timezone.utc)
        with self.assertRaises(UnauthorizedException) as context:
            await get_current_user(credentials, auth_service, user_repository)
        self.assertEqual(context.exception.error_code, "USER_ALREADY_WITHDRAWN")
        self.assertEqual(user_repository.find_by_id.await_count, 2)


if __name__ == "__main__":
    unittest.main()
