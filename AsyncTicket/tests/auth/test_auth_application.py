import unittest
from datetime import datetime, timedelta, timezone

from asyncticket.auth.application.service import (
    AuthApplicationService,
)
from asyncticket.auth.domain.entities import (
    BlacklistedToken,
)
from asyncticket.auth.domain.service import (
    AccessTokenPayload,
)
from asyncticket.auth.infrastructure.security import JwtTokenProvider
from asyncticket.shared.core.exceptions import (
    UnauthorizedException,
)
from asyncticket.users.domain.users import (
    User,
    UserRole,
)


class FakePasswordHasher:
    def hash(self, raw_password: str) -> str:
        return f"hashed:{raw_password}"

    def verify(
        self,
        raw_password: str,
        hashed_password: str,
    ) -> bool:
        return hashed_password == f"hashed:{raw_password}"


class FakeUserRepository:
    def __init__(self, user: User):
        self.user = user

    async def find_by_id(self, user_id: int):
        if self.user.user_id == user_id:
            return self.user

        return None

    async def find_by_email(self, email: str):
        if self.user.email == email:
            return self.user

        return None

    async def save(self, user: User):
        self.user = user
        return user


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
            role=UserRole.BUYER,
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

        self.user_repository = FakeUserRepository(
            self.user
        )
        self.blacklist_repository = (
            FakeBlacklistRepository()
        )
        self.token_provider = FakeTokenProvider()
        self.password_hasher = FakePasswordHasher()

        self.service = AuthApplicationService(
            user_repository=self.user_repository,
            token_blacklist_repository=(
                self.blacklist_repository
            ),
            token_provider=self.token_provider,
            password_hasher=self.password_hasher,
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
            user_repository=self.user_repository,
            token_blacklist_repository=self.blacklist_repository,
            token_provider=token_provider,
            password_hasher=self.password_hasher,
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
            user_repository=self.user_repository,
            token_blacklist_repository=self.blacklist_repository,
            token_provider=token_provider,
            password_hasher=self.password_hasher,
        )

        with self.assertRaises(UnauthorizedException):
            await service.authenticate(tampered_token)


if __name__ == "__main__":
    unittest.main()
