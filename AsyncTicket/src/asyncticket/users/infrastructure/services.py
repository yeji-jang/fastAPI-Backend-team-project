"""Auth가 요구하는 사용자 조회 계약의 SQLAlchemy 구현."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from asyncticket.auth.domain.service import (
    AuthAccount,
    AuthAccountReader,
    AuthRole,
)
from asyncticket.users.infrastructure.models import UserModel


class SqlAlchemyAuthAccountReader(AuthAccountReader):
    """users 테이블을 Auth 전용 최소 정보로 변환한다."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _to_auth_account(user: UserModel) -> AuthAccount:
        return AuthAccount(
            user_id=user.user_id,
            role=AuthRole(user.role),
            password_hash=user.password_hash,
            is_withdrawn=user.deleted_at is not None,
        )

    async def find_by_email(self, email: str) -> AuthAccount | None:
        user = await self.session.scalar(
            select(UserModel).where(
                UserModel.email == email.strip().lower()
            )
        )
        return None if user is None else self._to_auth_account(user)

    async def find_by_id(self, user_id: int) -> AuthAccount | None:
        user = await self.session.scalar(
            select(UserModel).where(UserModel.user_id == user_id)
        )
        return None if user is None else self._to_auth_account(user)
