import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum

from asyncticket.shared.core.exceptions import (
    BadRequestException,
    ForbiddenException,
    ValidationException,
)
from asyncticket.users.domain.service import PasswordHasher


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    SELLER = "SELLER"
    BUYER = "BUYER"


EMAIL_PATTERN = re.compile(
    r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
)

PASSWORD_PATTERN = re.compile(
    r"^(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*#?&])[A-Za-z\d@$!%*#?&]{8,128}$"
)


@dataclass
class User:
    user_id: int | None
    email: str
    name: str
    password_hash: str
    role: UserRole
    phone_number: str

    birth: date | None = None
    address: str | None = None
    address_detail: str | None = None
    post_no: str | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None

    def __post_init__(self) -> None:
        self.email = self.email.strip().lower()
        self.name = self.name.strip()
        self.phone_number = self.phone_number.strip()

        self.validate_email(self.email)
        self.validate_name(self.name)
        self.validate_phone_number(self.phone_number)

    @property
    def is_withdrawn(self) -> bool:
        """deleted_at이 있으면 탈퇴한 회원이다."""
        return self.deleted_at is not None

    @classmethod
    def create(
        cls,
        email: str,
        name: str,
        raw_password: str,
        phone_number: str,
        hasher: PasswordHasher,
        birth: date | None = None,
        address: str | None = None,
        address_detail: str | None = None,
        post_no: str | None = None,
    ) -> "User":
        email = email.strip().lower()
        name = name.strip()
        phone_number = phone_number.strip()

        cls.validate_email(email)
        cls.validate_name(name)
        cls.validate_password(raw_password)
        cls.validate_phone_number(phone_number)

        now = datetime.now(timezone.utc)

        return cls(
            user_id=None,
            email=email,
            name=name,
            password_hash=hasher.hash(raw_password),
            role=UserRole.BUYER,
            phone_number=phone_number,
            birth=birth,
            address=address,
            address_detail=address_detail,
            post_no=post_no,
            created_at=now,
        )

    def change_password(
        self,
        old_password: str,
        new_password: str,
        hasher: PasswordHasher,
    ) -> None:
        self._ensure_active()

        if not hasher.verify(old_password, self.password_hash):
            raise BadRequestException(
                message="기존 비밀번호가 일치하지 않습니다.",
                error_code="INVALID_OLD_PASSWORD",
            )

        if old_password == new_password:
            raise BadRequestException(
                message="기존 비밀번호와 동일한 비밀번호로 변경할 수 없습니다.",
                error_code="SAME_PASSWORD",
            )

        self.validate_password(new_password)

        self.password_hash = hasher.hash(new_password)
        self.updated_at = datetime.now(timezone.utc)

    def withdraw(self, requester: "User") -> None:
        self._ensure_active()
        requester.ensure_active()

        is_owner = (
            self.user_id is not None
            and self.user_id == requester.user_id
        )
        is_admin = requester.role == UserRole.ADMIN

        if not (is_owner or is_admin):
            raise ForbiddenException(
                message="본인 또는 관리자만 탈퇴할 수 있습니다.",
                error_code="WITHDRAW_PERMISSION_DENIED",
            )

        now = datetime.now(timezone.utc)
        self.deleted_at = now
        self.updated_at = now

    def _ensure_active(self) -> None:
        if self.is_withdrawn:
            raise ForbiddenException(
                message="탈퇴한 회원은 사용할 수 없습니다.",
                error_code="USER_ALREADY_WITHDRAWN",
            )

    def ensure_active(self) -> None:
        self._ensure_active()

    @staticmethod
    def validate_email(email: str) -> None:
        if not EMAIL_PATTERN.fullmatch(email):
            raise ValidationException(
                message="이메일 형식이 올바르지 않습니다.",
                error_code="INVALID_EMAIL",
                field_errors={
                    "email": ["올바른 이메일 형식을 입력하세요."]
                },
            )

    @staticmethod
    def validate_name(name: str) -> None:
        if not 2 <= len(name) <= 20:
            raise ValidationException(
                message="이름은 2자 이상 20자 이하여야 합니다.",
                error_code="INVALID_NAME",
                field_errors={
                    "name": ["이름은 2자 이상 20자 이하이어야 합니다."]
                },
            )

    @staticmethod
    def validate_phone_number(phone_number: str) -> None:
        if not phone_number:
            raise ValidationException(
                message="전화번호는 필수입니다.",
                error_code="INVALID_PHONE_NUMBER",
                field_errors={
                    "phone_number": ["전화번호를 입력하세요."]
                },
            )

        if len(phone_number) > 30:
            raise ValidationException(
                message="전화번호는 30자 이하이어야 합니다.",
                error_code="INVALID_PHONE_NUMBER",
                field_errors={
                    "phone_number": ["전화번호는 30자 이하이어야 합니다."]
                },
            )

    @staticmethod
    def validate_password(password: str) -> None:
        # bcrypt 계열 해시를 사용할 때의 72바이트 제한을 반영한다.
        if len(password.encode("utf-8")) > 72:
            raise ValidationException(
                message="비밀번호는 72바이트를 초과할 수 없습니다.",
                error_code="PASSWORD_TOO_LONG",
                field_errors={
                    "password": ["비밀번호는 72바이트 이하이어야 합니다."]
                },
            )

        if not PASSWORD_PATTERN.fullmatch(password):
            raise ValidationException(
                message="비밀번호 형식이 올바르지 않습니다.",
                error_code="INVALID_PASSWORD",
                field_errors={
                    "password": [
                        "비밀번호는 8~128자이며 "
                        "영문, 숫자, 특수문자를 포함해야 합니다."
                    ]
                },
            )
