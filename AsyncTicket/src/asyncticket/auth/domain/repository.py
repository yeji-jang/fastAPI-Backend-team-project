from datetime import datetime
from typing import Protocol

from asyncticket.auth.domain.entities import BlacklistedToken


class TokenBlacklistRepository(Protocol):
    async def save(self, token: BlacklistedToken) -> None:
        """폐기된 토큰을 저장한다."""
        ...

    async def exists(self, jti_token: str) -> bool:
        """토큰이 블랙리스트에 존재하는지 확인한다."""
        ...

    async def delete_expired(self, current_time: datetime) -> None:
        """만료된 블랙리스트 토큰을 삭제한다."""
        ...