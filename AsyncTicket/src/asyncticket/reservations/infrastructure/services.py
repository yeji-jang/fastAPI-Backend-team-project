"""
외부 데이터 조회 인터페이스 (구현)
    - domain/service.py의 약속을 SQLAlchemy로 구현
    - 다른 도메인 테이블(회차·좌석)을 읽어서 예매 도메인의 VO로 바꿔 돌려준다
    - 판단은 하지 않는다 (판단은 예매 엔티티와 application이 한다)
    - commit, flush 없음 : 조회만 한다
"""

from decimal import Decimal  # 좌석 가격이 int로 오기 때문에 Decimal로 바꿀 때 필요

# <sqlalchemy>
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# <Domain - 예매>
from asyncticket.reservations.domain.enums import ReservationStatus
from asyncticket.reservations.domain.reservation import ReservedPerformance, ReservedSeat
from asyncticket.reservations.domain.service import ReservedPerformanceReader, ReservedSeatReader, ReservationChecker, ReservationStatusReader   # 약속은 domain에서 가져옴


# <InfraStructure - 예매>
from asyncticket.reservations.infrastructure.models import ReservationModel

# <InfraStructure - 회차>
from asyncticket.performances.infrastructure.models import PerformanceModel

# <InfraStructure - 좌석>
from asyncticket.seats.infrastructure.repositories import SqlAlchemyPerformanceSeatRepository


# ---------- 기준 1 : 외부 데이터 참고 ----------

class SqlAlchemyReservationChecker(ReservationChecker):
    """한 회원은 한 회차에 예매대기·예매확정 예매를 1건만 가질 수 있다 (취소하면 다시 가능)"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def is_reserv_possible(self,
                                 ticketholder_id: int,
                                 perf_id: int) -> bool:
        # ① 이 회원 + 이 회차 + 진행 중(대기·확정)인 예매가 있는지 찾기
        statement = (
            select(ReservationModel.reserv_id)
            .where(
                ReservationModel.user_id == ticketholder_id,
                ReservationModel.perf_id == perf_id,
                ReservationModel.status.in_([
                    ReservationStatus.PENDING.value,
                    ReservationStatus.CONFIRMED.value,
                ]),
            )
            .limit(1)
        )
        result = await self.session.execute(statement)

        # ② 하나도 없으면 예매 가능
        return result.first() is None


class SqlAlchemyReservedPerformanceReader(ReservedPerformanceReader):
    """회차(performances) → 예매 VO(ReservedPerformance)"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_reserved_performance(self,
                                       perf_id: int) -> ReservedPerformance | None:
        # ① 회차 행 찾기 (회차 테이블 하나만 필요해서 JOIN 없이)
        statement = select(PerformanceModel).where(PerformanceModel.perf_id == perf_id)
        result = await self.session.execute(statement)
        row = result.scalar_one_or_none()

        # ② 없으면 None (application에서 404 처리)
        if row is None:
            return None

        # ③ 회차 컬럼 이름 → 예매 VO 이름으로 바꿔서 돌려줌
        return ReservedPerformance(
            reserved_perf_id=row.perf_id,
            perf_starts_at=row.starts_at,            # 공연 시작 → 취소 가능 시각
            reserv_opens_at=row.booking_opens_at,    # 예매 오픈 → 예매 생성 시작
            reserv_closes_at=row.booking_closes_at,  # 예매 마감 → 예매 생성 마감
        )


class SqlAlchemyReservedSeatReader(ReservedSeatReader):
    """좌석(performance_seats + seats_info) → 예매 VO(ReservedSeat)
    - 조회 SQL은 좌석 저장소(get_performance_seat_by_id)를 그대로 사용
    - 판매 가능 여부는 여기서 판단하지 않는다 (assign_reservation이 연결할 때 보장)"""

    def __init__(self, session: AsyncSession):
        self.seat_repository = SqlAlchemyPerformanceSeatRepository(session)

    async def get_reserved_seat(self,
                                perf_id: int,
                                perf_seat_id: int) -> ReservedSeat | None:
        # ① 좌석 저장소로 조회 (해당 회차의 좌석이 아니면 None)
        seat = await self.seat_repository.get_performance_seat_by_id(perf_id, perf_seat_id)

        # ② 없거나, 등급 가격이 아직 없는 좌석은 예매할 수 없음 → None
        if seat is None or seat["price"] is None:
            return None

        # ③ 좌석 값 → 예매 VO (가격은 int라서 Decimal로 변환)
        return ReservedSeat(
            reserved_seat_id=seat["perf_seat_id"],
            reserved_seat_price=Decimal(seat["price"]),
        )


# ---------- 기준 2 : 다른 도메인에 예매 데이터 제공 ----------

class SqlAlchemyReservationStatusReader(ReservationStatusReader):
    """다른 도메인(결제·좌석 등)이 예매 상태를 확인할 때 사용 | 예매가 없으면 None"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_reserved_status(self,
                                  reserv_id: int) -> ReservationStatus | None:
        # ① 예매 상태 컬럼 하나만 조회
        statement = select(ReservationModel.status).where(ReservationModel.reserv_id == reserv_id)
        result = await self.session.execute(statement)
        status = result.scalar_one_or_none()

        # ② 없으면 None, 있으면 DB 문자열 → enum
        return ReservationStatus(status) if status is not None else None