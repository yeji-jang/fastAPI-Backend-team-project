import unittest

from asyncticket.users.application.service import (
    UserApplicationService,
)
from asyncticket.users.domain.users import User


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
    def __init__(self):
        self.users = []
        self.next_id = 1

    async def find_by_id(self, user_id: int):
        for user in self.users:
            if user.user_id == user_id:
                return user

        return None

    async def find_by_email(self, email: str):
        for user in self.users:
            if user.email == email:
                return user

        return None

    async def save(self, user: User):
        if user.user_id is None:
            user.user_id = self.next_id
            self.next_id += 1
            self.users.append(user)

        return user


class UserApplicationTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_register_user(self):
        repository = FakeUserRepository()
        hasher = FakePasswordHasher()

        service = UserApplicationService(
            user_repository=repository,
            password_hasher=hasher,
        )

        user = await service.register_user(
            email="test@example.com",
            name="테스트",
            password="Password1!",
            phone_number="010-1234-5678",
        )

        self.assertEqual(user.user_id, 1)
        self.assertEqual(
            user.email,
            "test@example.com",
        )
        self.assertEqual(len(repository.users), 1)


if __name__ == "__main__":
    unittest.main()