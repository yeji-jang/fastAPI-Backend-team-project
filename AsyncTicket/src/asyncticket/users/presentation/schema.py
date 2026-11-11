from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from asyncticket.users.domain.users import UserRole


class SignUpRequest(BaseModel):
    email: EmailStr = Field(
        description="로그인에 사용할 이메일",
    )
    name: str = Field(
        min_length=2,
        max_length=20,
        description="회원 이름",
    )
    password: str = Field(
        min_length=8,
        max_length=128,
        description="비밀번호",
    )
    phone_number: str = Field(
        min_length=1,
        max_length=30,
        description="전화번호",
    )
    birth: date | None = Field(
        default=None,
        description="생년월일",
    )
    address: str | None = Field(
        default=None,
        max_length=255,
        description="기본 주소",
    )
    address_detail: str | None = Field(
        default=None,
        max_length=255,
        description="상세 주소",
    )
    post_no: str | None = Field(
        default=None,
        max_length=20,
        description="우편번호",
    )


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(
        description="현재 비밀번호",
    )
    new_password: str = Field(
        min_length=8,
        max_length=128,
        description="새 비밀번호",
    )


class UserResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
    )

    user_id: int
    email: EmailStr
    name: str
    role: UserRole
    phone_number: str
    birth: date | None
    address: str | None
    address_detail: str | None
    post_no: str | None
    created_at: datetime | None
    updated_at: datetime | None