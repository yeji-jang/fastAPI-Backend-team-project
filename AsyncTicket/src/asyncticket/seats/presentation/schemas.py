# <표현 계층 - 좌석 요청·응답 형식>
# - 요청은 자료형·범위를 검사하고, 응답 모델은 APIResponse의 data에 담는다.

from decimal import Decimal
from typing import Annotated
from asyncticket.seats.domain.enums import SeatGrade, SeatStatus
from asyncticket.seats.domain.seat_info import SeatInfo
from asyncticket.shared.core.exceptions import ValidationException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

SeatName = Annotated[str, StringConstraints(min_length=1, max_length=255)]
SeatPrice = Annotated[int, Field(strict=True, ge=0, le=2147483647)]


class SeatConfigurationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: SeatGrade
    total_seat: int = Field(strict=True, gt=0, le=2147483647)
    price: SeatPrice
    seat_seqs: list[SeatName]

    # 1) 좌석명·수량·중복 입력 검사
    @model_validator(mode="after")
    def validate_names(self):
        try:
            SeatInfo.validate_request_configuration(
                self.name, self.total_seat, self.seat_seqs
            )
        except ValidationException as error:
            # HTTP 입력은 기존 Pydantic 검증 응답으로 전달한다.
            raise ValueError(error.message) from error
        return self


class SeatPriceUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price: SeatPrice


class SeatInfoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seat_id: int
    perf_id: int
    name: str | None
    total_seat: int | None
    price: int | None


class SeatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    perf_seat_id: int
    seat_id: int
    perf_id: int
    grade: SeatGrade | None
    seat_seq: str | None
    price: int | None
    status: SeatStatus


class SeatListResponse(BaseModel):
    perf_id: int
    items: list[SeatResponse]


class ReservationSeatListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reserv_id: int
    quantity: int
    # 예매 전체의 구매 당시 금액이다. 좌석별 구매가로 복사하지 않는다.
    purchase_price: Decimal
    items: list[SeatResponse]
