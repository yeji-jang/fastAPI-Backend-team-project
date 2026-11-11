from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(
        description="가입한 이메일",
    )
    password: str = Field(
        description="비밀번호",
    )


class LoginResponse(BaseModel):
    access_token: str = Field(
        description="Access Token",
    )
    token_type: str = Field(
        default="bearer",
        description="인증 방식",
    )
    expires_at: str = Field(
        description="토큰 만료 시각",
    )
    user_id: int = Field(
        description="회원 ID",
    )