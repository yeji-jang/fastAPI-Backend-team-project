# <도메인 - 좌석 등급 규칙>
# - 회차·등급·수량·가격과 좌석명 규칙만 검사한다. DB 저장은 하지 않는다.

from dataclasses import dataclass, replace
from datetime import datetime
from asyncticket.shared.core.exceptions import (
    ConflictException,
    SharedException,
    NotFoundException,
    ValidationException,
)
from asyncticket.seats.domain.enums import SeatGrade, SeatStatus
from asyncticket.seats.domain.performance_seat import PerformanceSeat
from asyncticket.shared.domain.catalog import CatalogActor, CatalogPolicy


class SeatInfoNotFoundError(NotFoundException):
    """요청한 회차에서 다룰 수 없는 좌석 등급."""

    def __init__(self, message: str):
        super().__init__(message, error_code="SEAT_INFO_NOT_FOUND")


class SeatConfigurationConflictError(ConflictException):
    """현재 회차의 등급·좌석명과 충돌하는 구성."""


@dataclass(frozen=True, kw_only=True)
class SeatNames:
    """수량·형식·중복을 검사한 좌석명. 검증 후 원본 목록 변경의 영향을 받지 않는다."""

    total_seat: int
    values: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", tuple(self.values))
        if len(self.values) != self.total_seat:
            raise ValidationException("좌석명 개수와 등급 좌석 수가 일치해야 합니다.")
        for seat_seq in self.values:
            PerformanceSeat.validate_seat_seq(seat_seq)
        if len(set(self.values)) != len(self.values):
            raise ValidationException("중복된 좌석명이 있습니다.")


@dataclass(frozen=True, kw_only=True)
class SeatInfo:
    """특정 공연 회차의 좌석 등급."""

    perf_id: int
    name: SeatGrade
    total_seat: int
    price: int
    seat_id: int | None = None

    # 1) 등급을 만들 때 ID·등급·수량·가격 검사
    def __post_init__(self) -> None:
        if type(self.perf_id) is not int or self.perf_id <= 0:
            raise ValidationException("회차 ID는 1 이상이어야 합니다.")

        if self.seat_id is not None and (
            type(self.seat_id) is not int or self.seat_id <= 0
        ):
            raise ValidationException("좌석 등급 ID는 1 이상이어야 합니다.")

        if not isinstance(self.name, SeatGrade):
            raise ValidationException("좌석 등급은 SeatGrade 타입이어야 합니다.")

        if type(self.total_seat) is not int or self.total_seat <= 0:
            raise ValidationException("좌석 수는 1 이상이어야 합니다.")

        if type(self.price) is not int or self.price < 0:
            raise ValidationException("가격은 0 이상이어야 합니다.")

    # 2) 전체 좌석 수에서 점유 수를 빼 잔여 수 계산
    def remaining_seats(self, occupied_count: int) -> int:
        if type(occupied_count) is not int or occupied_count < 0:
            raise ValidationException("점유 좌석 수는 음수일 수 없습니다.")

        if occupied_count > self.total_seat:
            raise ValidationException("점유 좌석 수가 전체 좌석 수보다 많습니다.")

        return self.total_seat - occupied_count

    # 3) 요청 수량이 잔여 수량 이내인지 검사
    def require_capacity(self, quantity: int, occupied_count: int) -> None:
        if type(quantity) is not int or quantity <= 0:
            raise ValidationException("요청 매수는 1 이상이어야 합니다.")

        if quantity > self.remaining_seats(occupied_count):
            raise ValidationException("남은 좌석이 부족합니다.")

    # 4) 새 좌석 등급 생성
    @classmethod
    def create(
        cls,
        *,
        perf_id: int,
        name: SeatGrade,
        total_seat: int,
        price: int,
    ) -> "SeatInfo":
        return cls(
            perf_id=perf_id,
            name=name,
            total_seat=total_seat,
            price=price,
        )

    @staticmethod
    def validate_request_configuration(
        name: SeatGrade,
        total_seat: int,
        seat_seqs: list[str],
    ) -> None:
        # 요청에서는 기존과 같이 공백 → 수량 → 중복 순서로 검사한다.
        if not name.strip() or any(not seat_seq.strip() for seat_seq in seat_seqs):
            raise ValidationException("등급명과 좌석명은 공백일 수 없습니다.")
        SeatNames(total_seat=total_seat, values=tuple(seat_seqs))

    # 6) 저장된 등급 ID로 개별 좌석 생성
    def create_seats(self, seat_seqs: list[str] | SeatNames) -> list[PerformanceSeat]:
        if self.seat_id is None:
            raise ValidationException("등급을 먼저 저장해야 합니다.")
        names = (
            seat_seqs
            if isinstance(seat_seqs, SeatNames)
            else SeatNames(total_seat=self.total_seat, values=tuple(seat_seqs))
        )
        if names.total_seat != self.total_seat:
            raise ValidationException("좌석명 개수와 등급 좌석 수가 일치해야 합니다.")

        return [
            PerformanceSeat.create(
                seat_id=self.seat_id,
                seat_seq=seat_seq,
                # 초기 상태 AVAILABLE은 임시 기준이다.
                status=SeatStatus.AVAILABLE,
            )
            for seat_seq in names.values
        ]

    # 7) 저장된 등급만 수정 가능
    def require_saved_for_update(self) -> None:
        if self.seat_id is None:
            raise ValidationException("신규 등급은 좌석명과 함께 생성해야 합니다.")

    # 가격 변경도 생성 시의 가격 검증을 재사용한다.
    def update_price(self, price: int, *, perf_id: int | None = None) -> "SeatInfo":
        """요청한 회차의 등급만 가격을 변경한다."""
        if perf_id is not None and self.perf_id != perf_id:
            raise SeatInfoNotFoundError("해당 회차의 좌석 등급을 찾을 수 없습니다.")
        self.require_saved_for_update()
        return replace(self, price=price)

    # 10) 새 구성의 ID·좌석명 검사
    def require_new_configuration(self, seat_seqs: list[str]) -> SeatNames:
        if self.seat_id is not None:
            raise ValidationException("새 좌석 구성에는 등급 ID를 지정할 수 없습니다.")
        return SeatNames(total_seat=self.total_seat, values=tuple(seat_seqs))

    # 11) 저장소가 조회한 기존 등급 중복 여부로 판단
    def require_unique_grade(self, already_exists: bool) -> None:
        if already_exists:
            raise SeatConfigurationConflictError(
                "같은 회차에 이미 등록된 좌석 등급입니다."
            )

    # 12) 저장소가 조회한 기존 좌석명 중복 여부로 판단
    def require_unique_seat_names(self, already_exists: bool) -> None:
        if already_exists:
            raise SeatConfigurationConflictError(
                "같은 회차에 이미 등록된 좌석명입니다."
            )


@dataclass(frozen=True, kw_only=True)
class SeatManagement:
    """외부에서 조회한 소유자·판매 시각을 좌석 관리 규칙으로 판단한다."""

    owner_id: int
    booking_opens_at: datetime

    def __post_init__(self) -> None:
        if type(self.owner_id) is not int or self.owner_id <= 0:
            raise SharedException(
                "공연 소유자 설정을 확인해야 합니다.",
                status_code=503,
                error_code="INVALID_SHOW_OWNER",
            )

    def authorize_change(
        self,
        actor: CatalogActor,
        policy: CatalogPolicy,
        *,
        now: datetime,
    ) -> None:
        """기존 정책의 소유권을 확인한 뒤 판매 시작 전 변경만 허용한다."""
        policy.authorize(actor, self.owner_id)
        self.require_before_sale(now)

    def require_before_sale(self, now: datetime) -> None:
        if (
            not isinstance(self.booking_opens_at, datetime)
            or self.booking_opens_at.utcoffset() is None
        ):
            raise SharedException(
                "회차 판매 시각 설정을 확인해야 합니다.",
                status_code=503,
                error_code="INVALID_BOOKING_TIME",
            )
        if now >= self.booking_opens_at:
            raise ConflictException(
                "판매 시작 후 좌석 구성을 변경할 수 없습니다.",
                error_code="SEAT_SALE_STARTED",
            )
