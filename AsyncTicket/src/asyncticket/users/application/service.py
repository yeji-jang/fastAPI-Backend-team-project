from datetime import date

from asyncticket.shared.core.exceptions import (
    ConflictException,
    NotFoundException,
)
from asyncticket.users.domain.repository import UserRepository
from asyncticket.users.domain.service import PasswordHasher
from asyncticket.users.domain.users import User


class UserApplicationService:
    def __init__(
        self,
        user_repository: UserRepository,
        password_hasher: PasswordHasher,
    ) -> None:
        self.user_repository = user_repository
        self.password_hasher = password_hasher

    async def register_user(
        self,
        email: str,
        name: str,
        password: str,
        phone_number: str,
        birth: date | None = None,
        address: str | None = None,
        address_detail: str | None = None,
        post_no: str | None = None,
    ) -> User:
        """
        회원가입을 처리한다.

        처리 순서:
        1. 이메일 중복 확인
        2. User Domain 객체 생성
        3. 비밀번호 해시
        4. 회원 저장
        """

        normalized_email = email.strip().lower()

        existing_user = await self.user_repository.find_by_email(
            normalized_email
        )

        if existing_user is not None:
            raise ConflictException(
                message="이미 사용 중인 이메일입니다.",
                error_code="EMAIL_ALREADY_EXISTS",
            )

        user = User.create(
            email=normalized_email,
            name=name,
            raw_password=password,
            phone_number=phone_number,
            hasher=self.password_hasher,
            birth=birth,
            address=address,
            address_detail=address_detail,
            post_no=post_no,
        )

        return await self.user_repository.save(user)

    async def get_user_by_id(self, user_id: int) -> User:
        """회원 ID로 회원을 조회한다."""

        user = await self.user_repository.find_by_id(user_id)

        if user is None:
            raise NotFoundException(
                message="회원을 찾을 수 없습니다.",
                error_code="USER_NOT_FOUND",
            )

        return user

    async def get_user_by_email(self, email: str) -> User:
        """이메일로 회원을 조회한다."""

        user = await self.user_repository.find_by_email(
            email.strip().lower()
        )

        if user is None:
            raise NotFoundException(
                message="회원을 찾을 수 없습니다.",
                error_code="USER_NOT_FOUND",
            )

        return user

    async def change_password(
        self,
        user_id: int,
        old_password: str,
        new_password: str,
    ) -> User:
        """
        비밀번호를 변경한다.

        실제 비즈니스 검증은 User Domain의 change_password가 수행한다.
        """

        user = await self.get_user_by_id(user_id)

        user.change_password(
            old_password=old_password,
            new_password=new_password,
            hasher=self.password_hasher,
        )

        return await self.user_repository.save(user)

    async def withdraw_user(
        self,
        target_user_id: int,
        requester_user_id: int,
    ) -> User:
        """
        회원 탈퇴를 처리한다.

        탈퇴 대상 회원과 요청자를 각각 조회한 뒤,
        실제 권한 판단은 User Domain에 위임한다.
        """

        target_user = await self.get_user_by_id(target_user_id)
        requester = await self.get_user_by_id(requester_user_id)

        target_user.withdraw(requester)

        return await self.user_repository.save(target_user)

    async def ensure_active_user(self, user: User) -> User:
        """
        탈퇴 회원의 접근을 차단한다.

        User Domain의 내부 규칙을 사용하기 위해
        현재 상태를 확인한다.
        """

        user.ensure_active()
        return user
