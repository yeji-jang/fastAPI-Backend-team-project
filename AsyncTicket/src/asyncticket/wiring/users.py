# Users 도메인 의존성 조립

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from asyncticket.shared.core.database import get_db
from asyncticket.users.application.service import (
    UserApplicationService,
)
from asyncticket.users.domain.repository import UserRepository
from asyncticket.users.domain.service import PasswordHasher
from asyncticket.users.infrastructure.repositories import (
    SqlAlchemyUserRepository,
)
from asyncticket.users.infrastructure.security import (
    BcryptPasswordHasher,
)


DatabaseSession = Annotated[
    AsyncSession,
    Depends(get_db),
]


def get_user_repository(
    session: DatabaseSession,
) -> UserRepository:
    return SqlAlchemyUserRepository(session)


def get_password_hasher() -> PasswordHasher:
    return BcryptPasswordHasher()


def get_user_service(
    user_repository: Annotated[
        UserRepository,
        Depends(get_user_repository),
    ],
    hasher: Annotated[
        PasswordHasher,
        Depends(get_password_hasher),
    ],
) -> UserApplicationService:
    return UserApplicationService(
        user_repository=user_repository,
        password_hasher=hasher,
    )