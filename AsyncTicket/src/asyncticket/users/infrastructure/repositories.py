from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from asyncticket.users.domain.repository import UserRepository
from asyncticket.users.domain.users import User
from asyncticket.users.infrastructure.models import UserModel


class SqlAlchemyUserRepository(UserRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_by_id(self, user_id: int) -> User | None:
        statement = select(UserModel).where(
            UserModel.user_id == user_id
        )

        user_model = await self.session.scalar(statement)

        if user_model is None:
            return None

        return user_model.to_domain()

    async def find_by_email(self, email: str) -> User | None:
        statement = select(UserModel).where(
            UserModel.email == email.strip().lower()
        )

        user_model = await self.session.scalar(statement)

        if user_model is None:
            return None

        return user_model.to_domain()

    async def save(self, user: User) -> User:
        if user.user_id is None:
            return await self._insert(user)

        return await self._update(user)

    async def _insert(self, user: User) -> User:
        user_model = UserModel(
            email=user.email,
            password_hash=user.password_hash,
            name=user.name,
            role=user.role.value,
            phone_number=user.phone_number,
            birth=user.birth,
            address=user.address,
            address_detail=user.address_detail,
            post_no=user.post_no,
            created_at=user.created_at,
            updated_at=user.updated_at,
            deleted_at=user.deleted_at,
        )

        self.session.add(user_model)

        await self.session.flush()
        await self.session.refresh(user_model)

        return user_model.to_domain()

    async def _update(self, user: User) -> User:
        statement = select(UserModel).where(
            UserModel.user_id == user.user_id
        )

        user_model = await self.session.scalar(statement)

        if user_model is None:
            return await self._insert(user)

        # 이메일과 권한은 일반 사용자 수정에서 변경하지 않는다.
        user_model.name = user.name
        user_model.password_hash = user.password_hash
        user_model.phone_number = user.phone_number
        user_model.birth = user.birth
        user_model.address = user.address
        user_model.address_detail = user.address_detail
        user_model.post_no = user.post_no
        user_model.updated_at = user.updated_at
        user_model.deleted_at = user.deleted_at

        await self.session.flush()
        await self.session.refresh(user_model)

        return user_model.to_domain()