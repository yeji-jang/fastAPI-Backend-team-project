"""표현 계층: 공연 API 요청을 검증하고 공개 응답 필드를 제한한다."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from asyncticket.shared.presentation.catalog_schemas import PatchRequest

PositiveId = Annotated[int, Field(gt=0, le=9223372036854775807, strict=True)]
PositiveInt = Annotated[int, Field(gt=0, le=2147483647, strict=True)]
ShowTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
ShowType = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class ShowCreateRequest(BaseModel):
    """소유자·ID·생성시각은 서버가 정하므로 입력으로 허용하지 않는다."""

    model_config = ConfigDict(extra="forbid")
    venues_id: PositiveId = Field(description="공연장 ID")
    title: ShowTitle = Field(description="공연명")
    description: str | None = Field(default=None, description="공연 소개")
    performer: str | None = Field(default=None, max_length=255, description="출연자")
    type: ShowType = Field(description="공연 분류")
    runtime: PositiveInt | None = Field(default=None, description="공연 시간(분)")


class ShowUpdateRequest(PatchRequest):
    """생략은 유지, nullable 필드의 명시적 null은 값 비우기로 처리한다."""

    venues_id: PositiveId | None = Field(default=None, description="변경할 공연장 ID")
    title: ShowTitle | None = Field(default=None, description="변경할 공연명")
    description: str | None = Field(default=None, description="변경할 공연 소개")
    performer: str | None = Field(default=None, max_length=255, description="변경할 출연자")
    type: ShowType | None = Field(default=None, description="변경할 공연 분류")
    runtime: PositiveInt | None = Field(default=None, description="변경할 공연 시간(분)")


class ShowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    show_id: int = Field(description="공연 ID")
    venues_id: int = Field(description="공연장 ID")
    title: str = Field(description="공연명")
    description: str | None = Field(description="공연 소개")
    performer: str | None = Field(description="출연자")
    type: str = Field(description="공연 분류")
    runtime: int | None = Field(description="공연 시간")
    created_at: datetime = Field(description="등록 시각")
    updated_at: datetime | None = Field(description="수정 시각")


class ShowListResponse(BaseModel):
    items: list[ShowResponse] = Field(description="공연 목록")
    page: int = Field(description="현재 페이지")
    size: int = Field(description="페이지 크기")
    total: int = Field(description="필터에 일치하는 전체 공연 수")
