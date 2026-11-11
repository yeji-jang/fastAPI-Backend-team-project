"""표현 계층: 회차 생성·부분 수정 입력과 응답 형식을 정의한다."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from asyncticket.shared.presentation.catalog_schemas import IsoDatetime, PatchRequest

PositiveInt = Annotated[int, Field(gt=0, le=2147483647, strict=True)]
PerformanceStatus = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]


class PerformanceCreateRequest(BaseModel):
    """회차 소속은 URL, 회차 ID는 서버가 정한다. status 예시를 Enum으로 고정하지 않는다."""

    model_config = ConfigDict(extra="forbid")
    round_number: PositiveInt = Field(description="공연 안의 회차 번호")
    starts_at: IsoDatetime = Field(description="공연 시작 시각(시간대 필수)")
    ends_at: IsoDatetime = Field(description="공연 종료 시각(시간대 필수)")
    booking_opens_at: IsoDatetime = Field(description="예매 시작 시각(시간대 필수)")
    booking_closes_at: IsoDatetime = Field(description="예매 마감 시각(시간대 필수)")
    max_tickets_per_user: PositiveInt = Field(default=3, description="1인당 예매 가능 매수")
    status: PerformanceStatus = Field(description="회차 운영 상태")


class PerformanceUpdateRequest(PatchRequest):
    """일부 입력은 응용 계층에서 기존 값과 합친 뒤 전체 시간순서를 검사한다."""

    round_number: PositiveInt | None = Field(default=None, description="변경할 회차 번호")
    starts_at: IsoDatetime | None = Field(default=None, description="변경할 공연 시작 시각")
    ends_at: IsoDatetime | None = Field(default=None, description="변경할 공연 종료 시각")
    booking_opens_at: IsoDatetime | None = Field(default=None, description="변경할 예매 시작 시각")
    booking_closes_at: IsoDatetime | None = Field(default=None, description="변경할 예매 마감 시각")
    max_tickets_per_user: PositiveInt | None = Field(default=None, description="변경할 매수 제한")
    status: PerformanceStatus | None = Field(default=None, description="변경할 회차 상태")


class PerformanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    perf_id: int = Field(description="공연 회차 ID")
    show_id: int = Field(description="공연 ID")
    round_number: int = Field(description="회차 번호")
    starts_at: datetime = Field(description="공연 시작 시각")
    ends_at: datetime = Field(description="공연 종료 시각")
    booking_opens_at: datetime = Field(description="예매 시작 시각")
    booking_closes_at: datetime = Field(description="예매 마감 시각")
    max_tickets_per_user: int = Field(description="1인당 예매 가능 매수")
    status: str = Field(description="회차 운영 상태")


class PerformanceListResponse(BaseModel):
    items: list[PerformanceResponse] = Field(description="공연 회차 목록")
