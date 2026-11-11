from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class AuthRole(StrEnum):
    ADMIN = "ADMIN"
    SELLER = "SELLER"
    BUYER = "BUYER"


@dataclass(frozen=True)
class AccessTokenPayload:
    access_token: str
    user_id: int
    role: AuthRole
    jti: str
    expires_at: datetime


@dataclass(frozen=True)
class AuthAccount:
    user_id: int
    role: AuthRole
    password_hash: str
    is_withdrawn: bool


class TokenProvider(Protocol):
    def issue_access_token(
        self,
        user_id: int,
        role: AuthRole,
    ) -> AccessTokenPayload:
        ...

    def verify_access_token(
        self,
        token: str,
    ) -> AccessTokenPayload:
        ...


class AuthAccountReader(Protocol):
    """Auth가 외부 사용자 데이터에 요구하는 조회 계약."""

    async def find_by_email(self, email: str) -> AuthAccount | None:
        ...

    async def find_by_id(self, user_id: int) -> AuthAccount | None:
        ...


class PasswordVerifier(Protocol):
    def verify(self, raw_password: str, hashed_password: str) -> bool:
        ...
