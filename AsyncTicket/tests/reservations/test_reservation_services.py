"""
예매 외부 데이터 조회 구현(infrastructure/services.py)을 SQLite 메모리 DB로 확인

<테스트 읽는 법>
- 테스트마다 빈 메모리 DB를 새로 만들고, 회차 2개(10번, 20번)를 미리 넣어 둔다
- 1) 준비 : 예매·좌석 데이터를 넣는다
  2) 실행 : Checker / Reader 메서드를 호출한다
  3) 확인 : 돌려받은 값(bool, VO, enum, None)이 기대한 값인지 assert로 비교한다

<SQLite와 PostgreSQL의 차이 (테스트에서만 맞춰 주는 것)>
- 비동기 SQLite 드라이버(aiosqlite)가 없어서, 동기 Session을 await로 부를 수 있게 감싼다
- SQLite는 시각의 타임존을 저장하지 않는다 → DB에서 꺼낸 시각은 타임존 없이 비교한다

<실행 방법> (AsyncTicket 폴더에서)
    .venv\\Scripts\\python -m unittest tests.test_reservation_services -v
"""

import unittest
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from asyncticket.shared.core.models import Base, init_models
from asyncticket.reservations.domain.enums import ReservationStatus
from asyncticket.reservations.domain.reservation import ReservedPerformance, ReservedSeat
from asyncticket.reservations.infrastructure.models import ReservationModel
from asyncticket.reservations.infrastructure.services import (
    SqlAlchemyReservationChecker,
    SqlAlchemyReservedPerformanceReader,
    SqlAlchemyReservedSeatReader,
    SqlAlchemyReservationStatusReader,
)
from asyncticket.performances.infrastructure.models import PerformanceModel
from asyncticket.seats.infrastructure.models import SeatsInfoModel, PerformanceSeats

UTC = timezone.utc
PERF_ID = 10        # 기본 회차
OTHER_PERF_ID = 20  # 다른 회차
OWNER_ID = 1
OTHER_ID = 2


class SyncSessionAdapter:
    """동기 Session을 AsyncSession처럼 await로 부를 수 있게 감싼다 (테스트 전용)"""

    def __init__(self, session: Session):
        self._session = session

    async def execute(self, statement):
        return self._session.execute(statement)


class ReservationServicesTests(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        """테스트마다 빈 메모리 DB를 만들고, 회차 2개를 넣어 둔다"""
        init_models()
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine, tables=[
            ReservationModel.__table__,
            PerformanceModel.__table__,
            SeatsInfoModel.__table__,
            PerformanceSeats.__table__,
        ])
        self.db = Session(self.engine)
        for perf_id in (PERF_ID, OTHER_PERF_ID):
            self.db.add(PerformanceModel(
                perf_id=perf_id, show_id=1, round_number=1, status="SCHEDULED",
                starts_at=datetime(2026, 12, 1, 19, tzinfo=UTC),
                ends_at=datetime(2026, 12, 1, 21, tzinfo=UTC),
                booking_opens_at=datetime(2026, 11, 1, tzinfo=UTC),
                booking_closes_at=datetime(2026, 11, 30, tzinfo=UTC),
            ))
        self.db.flush()

        session = SyncSessionAdapter(self.db)
        self.checker = SqlAlchemyReservationChecker(session)
        self.performance_reader = SqlAlchemyReservedPerformanceReader(session)
        self.seat_reader = SqlAlchemyReservedSeatReader(session)
        self.status_reader = SqlAlchemyReservationStatusReader(session)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def insert_reservation(self, *, reserv_id, user_id=OWNER_ID, perf_id=PERF_ID, status="CONFIRMED"):
        """테스트용 예매 행을 DB에 직접 넣는 도우미"""
        self.db.add(ReservationModel(
            reserv_id=reserv_id, order_number=f"ORD-{reserv_id}", user_id=user_id,
            perf_id=perf_id, quantity=1, total_amount=Decimal("150000"), status=status,
        ))
        self.db.flush()

    def insert_seat(self, *, perf_seat_id, seat_id, perf_id=PERF_ID, price=150000):
        """테스트용 좌석 등급(seats_info) + 개별 좌석(performance_seats)을 넣는 도우미"""
        self.db.add(SeatsInfoModel(seat_id=seat_id, perf_id=perf_id, name="VIP", total_seat=10, price=price))
        self.db.flush()
        self.db.add(PerformanceSeats(perf_seat_id=perf_seat_id, seat_id2=seat_id, status="AVAILABLE", seat_seq="A1"))
        self.db.flush()

    # =========================================================
    # 1) ReservationChecker : 한 회원은 한 회차에 대기·확정 예매 1건만
    # =========================================================
    async def test_예매가_없으면_예매할_수_있다(self):
        self.assertTrue(await self.checker.is_reserv_possible(OWNER_ID, PERF_ID))

    async def test_예매대기가_있으면_예매할_수_없다(self):
        # 결제 중에 같은 회차를 또 예매하는 것을 막는다
        self.insert_reservation(reserv_id=1, status="PENDING")

        self.assertFalse(await self.checker.is_reserv_possible(OWNER_ID, PERF_ID))

    async def test_예매확정이_있으면_예매할_수_없다(self):
        self.insert_reservation(reserv_id=1, status="CONFIRMED")

        self.assertFalse(await self.checker.is_reserv_possible(OWNER_ID, PERF_ID))

    async def test_취소한_예매만_있으면_다시_예매할_수_있다(self):
        self.insert_reservation(reserv_id=1, status="CANCELED")

        self.assertTrue(await self.checker.is_reserv_possible(OWNER_ID, PERF_ID))

    async def test_다른_회원이나_다른_회차의_예매는_상관없다(self):
        self.insert_reservation(reserv_id=1, user_id=OTHER_ID, status="CONFIRMED")         # 다른 회원
        self.insert_reservation(reserv_id=2, perf_id=OTHER_PERF_ID, status="CONFIRMED")    # 다른 회차

        self.assertTrue(await self.checker.is_reserv_possible(OWNER_ID, PERF_ID))

    # =========================================================
    # 2) ReservedPerformanceReader : 회차 → ReservedPerformance
    # =========================================================
    async def test_회차를_예매_VO로_바꿔준다(self):
        performance = await self.performance_reader.get_reserved_performance(PERF_ID)

        # 회차 컬럼 이름 → 예매 VO 이름 (SQLite는 타임존을 버려서 타임존 없이 비교)
        self.assertEqual(performance, ReservedPerformance(
            reserved_perf_id=PERF_ID,
            perf_starts_at=datetime(2026, 12, 1, 19),     # starts_at
            reserv_opens_at=datetime(2026, 11, 1),        # booking_opens_at
            reserv_closes_at=datetime(2026, 11, 30),      # booking_closes_at
        ))

    async def test_없는_회차는_None(self):
        self.assertIsNone(await self.performance_reader.get_reserved_performance(999))

    # =========================================================
    # 3) ReservedSeatReader : 좌석 → ReservedSeat
    # =========================================================
    async def test_해당_회차의_좌석을_예매_VO로_바꿔준다(self):
        self.insert_seat(perf_seat_id=100, seat_id=1, price=150000)

        seat = await self.seat_reader.get_reserved_seat(PERF_ID, 100)

        # 가격은 int → Decimal
        self.assertEqual(seat, ReservedSeat(reserved_seat_id=100, reserved_seat_price=Decimal("150000")))

    async def test_다른_회차의_좌석은_None(self):
        # 20번 회차의 좌석을 10번 회차로 조회 → 해당 회차의 좌석이 아님
        self.insert_seat(perf_seat_id=200, seat_id=2, perf_id=OTHER_PERF_ID)

        self.assertIsNone(await self.seat_reader.get_reserved_seat(PERF_ID, 200))

    async def test_가격이_없는_좌석은_None(self):
        # 등급 가격이 아직 정해지지 않은 좌석은 예매할 수 없음
        self.insert_seat(perf_seat_id=101, seat_id=3, price=None)

        self.assertIsNone(await self.seat_reader.get_reserved_seat(PERF_ID, 101))

    async def test_없는_좌석은_None(self):
        self.assertIsNone(await self.seat_reader.get_reserved_seat(PERF_ID, 999))

    # =========================================================
    # 4) ReservationStatusReader : 다른 도메인에 예매 상태 제공
    # =========================================================
    async def test_예매_상태를_enum으로_알려준다(self):
        self.insert_reservation(reserv_id=1, status="PENDING")
        self.insert_reservation(reserv_id=2, status="CONFIRMED")
        self.insert_reservation(reserv_id=3, status="CANCELED")

        # DB 문자열 → enum
        self.assertEqual(await self.status_reader.get_reserved_status(1), ReservationStatus.PENDING)
        self.assertEqual(await self.status_reader.get_reserved_status(2), ReservationStatus.CONFIRMED)
        self.assertEqual(await self.status_reader.get_reserved_status(3), ReservationStatus.CANCELED)

    async def test_없는_예매의_상태는_None(self):
        self.assertIsNone(await self.status_reader.get_reserved_status(999))


if __name__ == "__main__":
    unittest.main()
