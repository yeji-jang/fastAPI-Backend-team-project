from typing import Protocol

from asyncticket.users.domain.users import User


class UserRepository(Protocol):
    async def find_by_id(self, user_id: int) -> User | None:
        """회원 ID로 회원을 조회한다."""
        ...

    async def find_by_email(self, email: str) -> User | None:
        """이메일로 회원을 조회한다."""
        ...

    async def save(self, user: User) -> User:
        """회원을 저장하고 저장된 회원을 반환한다."""
        ...