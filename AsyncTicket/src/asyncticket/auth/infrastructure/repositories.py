from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from asyncticket.auth.domain.entities import BlacklistedToken
from asyncticket.auth.domain.repository import TokenBlacklistRepository
from asyncticket.auth.infrastructure.models import BlacklistModel


class SqlAlchemyTokenBlacklistRepository(
    TokenBlacklistRepository
):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, token: BlacklistedToken) -> None:
        existing_token = await self.session.scalar(
            select(BlacklistModel).where(
                BlacklistModel.jti_token == token.jti_token
            )
        )

        # 같은 토큰으로 logout이 여러 번 호출되어도
        # 중복 PK 오류가 발생하지 않게 한다.
        if existing_token is not None:
            return

        token_model = BlacklistModel(
            jti_token=token.jti_token,
            expired_at=token.expired_at,
        )

        self.session.add(token_model)
        await self.session.flush()

    async def exists(self, jti_token: str) -> bool:
        statement = select(BlacklistModel.jti_token).where(
            BlacklistModel.jti_token == jti_token
        )

        result = await self.session.scalar(statement)

        return result is not None

    async def delete_expired(
        self,
        current_time: datetime,
    ) -> None:
        statement = delete(BlacklistModel).where(
            BlacklistModel.expired_at <= current_time
        )

        await self.session.execute(statement)
        await self.session.flush()