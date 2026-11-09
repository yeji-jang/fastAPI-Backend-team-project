# <인프라 - 좌석 테이블 매핑>
# - seats_info는 등급·가격, performance_seats는 개별 좌석·예매 FK를 저장한다.

from sqlalchemy import BigInteger, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from asyncticket.seats.domain.enums import SeatGrade, SeatStatus
from asyncticket.seats.domain.performance_seat import PerformanceSeat
from asyncticket.seats.domain.seat_info import SeatInfo
from asyncticket.shared.core.models import Base
from asyncticket.shared.core.exceptions import ValidationException


class SeatsInfoModel(Base):
    __tablename__ = "seats_info"

    seat_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    perf_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("performances.perf_id"),
        nullable=False,
    )
    # 기존 ERD의 nullable 컬럼은 유지한다. 미설정 행은 SeatInfo로 변환할 수 없다.
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    total_seat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 1) DB 행 → 좌석 등급 도메인 변환
    def to_seat_info(self) -> SeatInfo:
        # nullable DB 행의 복원 방어다. 정상 값의 업무 규칙은 SeatInfo가 검사한다.
        if self.name is None:
            raise ValueError("좌석 등급명은 공백이 아닌 1~255자여야 합니다.")
        if self.total_seat is None:
            raise ValueError("좌석 수는 1 이상이어야 합니다.")
        if self.price is None:
            raise ValueError("가격이 설정되지 않았습니다.")
        try:
            return SeatInfo(
                seat_id=self.seat_id,
                perf_id=self.perf_id,  # to_seat_info() 안
                name=SeatGrade(self.name),
                total_seat=self.total_seat,
                price=self.price,
            )
        except ValidationException as error:
            # DB 복원 실패는 요청 입력 오류(422)가 아닌 서버 오류로 전달한다.
            raise ValueError("저장된 좌석 등급 정보가 유효하지 않습니다.") from error


class PerformanceSeats(Base):
    __tablename__ = "performance_seats"

    perf_seat_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    seat_id2: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("seats_info.seat_id"),
        nullable=False,
    )
    reserv_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("reservations.reserv_id"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    seat_seq: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # 1) DB 행 → 개별 좌석 도메인 변환
    def to_performance_seat(self) -> PerformanceSeat:
        # 미설정 DB 값과 사용자 입력 오류를 구분하고, 나머지는 도메인에 위임한다.
        if self.seat_seq is None:
            raise ValueError("좌석명은 공백이 아닌 1~255자여야 합니다.")
        try:
            return PerformanceSeat(
                perf_seat_id=self.perf_seat_id,
                seat_id=self.seat_id2,
                reserv_id=self.reserv_id,
                status=SeatStatus(self.status),
                seat_seq=self.seat_seq,
            )
        except ValidationException as error:
            # DB 복원 실패는 요청 입력 오류(422)가 아닌 서버 오류로 전달한다.
            raise ValueError("저장된 개별 좌석 정보가 유효하지 않습니다.") from error
