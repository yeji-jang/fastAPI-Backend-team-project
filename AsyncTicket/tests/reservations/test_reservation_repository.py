"""
예매 저장소(SqlAlchemyReservationRepository)를 SQLite 메모리 DB로 확인

<테스트 읽는 법>
- 테스트마다 빈 메모리 DB를 새로 만들고, 회차 1개를 미리 넣어 둔다
- 1) 준비 : 예매·좌석·결제 데이터를 넣는다
  2) 실행 : 저장소 메서드를 호출한다
  3) 확인 : 돌려받은 예매 엔티티가 기대한 값인지 assert로 비교한다

<SQLite를 동기 세션으로 쓰는 이유>
- 저장소는 AsyncSession(await)을 쓰는데, 비동기 SQLite 드라이버(aiosqlite)는 프로젝트 의존성에 없다
- 그래서 동기 Session을 await로 부를 수 있게 감싼 SyncSessionAdapter를 넣어 준다
- 저장소 코드는 그대로 실행되므로 SELECT·JOIN·엔티티 변환을 실제로 확인할 수 있다

<SQLite와 PostgreSQL의 차이 (테스트에서만 맞춰 주는 것)>
- SQLite는 INTEGER PRIMARY KEY만 자동 증가한다 → 이 테스트에서만 BIGINT를 INTEGER로 만든다
- SQLite는 시각의 타임존을 저장하지 않는다 → DB에서 꺼낸 시각과 비교하는 취소 테스트는 타임존 없는 시각을 쓴다

<실행 방법> (AsyncTicket 폴더에서)
    uv run python -m unittest tests.test_reservation_repository -v
"""

import unittest
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from asyncticket.shared.core.models import Base, init_models
from asyncticket.reservations.domain.enums import ReservationStatus
from asyncticket.reservations.domain.reservation import (
    Reservation, TicketHolder, ReservedPerformance, ReservedSeat, ReservedPayment
)
from asyncticket.reservations.infrastructure.models import ReservationModel
from asyncticket.reservations.infrastructure.repositories import SqlAlchemyReservationRepository
from asyncticket.performances.infrastructure.models import PerformanceModel
from asyncticket.seats.infrastructure.models import PerformanceSeats
from asyncticket.payment.infrastructure.models import Payment as PaymentModel

UTC = timezone.utc
PERF_ID = 10
OWNER_ID = 1
OTHER_ID = 2


@compiles(BigInteger, "sqlite")
def _bigint_as_integer_on_sqlite(type_, compiler, **kw):
    """SQLite에서만 BIGINT를 INTEGER로 만든다 (PostgreSQL은 BIGINT 그대로 자동 증가)"""
    return "INTEGER"


class SyncSessionAdapter:
    """동기 Session을 AsyncSession처럼 await로 부를 수 있게 감싼다 (테스트 전용)"""

    def __init__(self, session: Session):
        self._session = session

    def add(self, obj):
        self._session.add(obj)

    async def flush(self):
        self._session.flush()

    async def execute(self, statement):
        return self._session.execute(statement)


class ReservationRepositoryTests(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        """테스트마다 빈 메모리 DB를 만들고, 회차 1개를 넣어 둔다"""
        init_models()
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine, tables=[
            ReservationModel.__table__,
            PerformanceModel.__table__,
            PerformanceSeats.__table__,
            PaymentModel.__table__,
        ])
        self.db = Session(self.engine)
        self.db.add(PerformanceModel(
            perf_id=PERF_ID, show_id=1, round_number=1, status="SCHEDULED",
            starts_at=datetime(2026, 12, 1, 19, tzinfo=UTC),
            ends_at=datetime(2026, 12, 1, 21, tzinfo=UTC),
            booking_opens_at=datetime(2026, 11, 1, tzinfo=UTC),
            booking_closes_at=datetime(2026, 11, 30, tzinfo=UTC),
        ))
        self.db.flush()

        self.repository = SqlAlchemyReservationRepository(SyncSessionAdapter(self.db))

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def insert_reservation(self, *, reserv_id, user_id=OWNER_ID, status="CONFIRMED",
                           created_at=datetime(2026, 11, 5, tzinfo=UTC),confirmed=True):
        """테스트용 예매 행을 DB에 직접 넣는 도우미 (confirmed=False면 확정 일시 없이)"""
        self.db.add(ReservationModel(
            reserv_id=reserv_id, order_number=f"ORD-{reserv_id}", user_id=user_id,
            perf_id=PERF_ID, quantity=1, total_amount=Decimal("150000"), status=status,
            created_at=created_at, confirmed_at=created_at if confirmed else None,
        ))
        self.db.flush()

    def link_seat_and_payment(self, *, reserv_id, perf_seat_id, pay_id):
        """좌석·결제 쪽에서 예매 ID로 연결하는 도우미"""
        self.db.add(PerformanceSeats(
            perf_seat_id=perf_seat_id, reserv_id=reserv_id, seat_id2=1, status="SOLD", seat_seq="A1",
        ))
        self.db.add(PaymentModel(
            pay_id=pay_id, reserv_id=reserv_id, method="CARD", amount=Decimal("150000"), status="SUCCESS",
        ))
        self.db.flush()

    # =========================================================
    # 1) reserv_add : 예매 저장
    # =========================================================
    async def test_저장하면_reserv_id와_created_at이_채워진다(self):
        # 준비 : 아직 DB에 없는 새 예매 (reserv_id, created_at 없음)
        reservation = Reservation.create_pending(
            ticketholder=TicketHolder(ticketholder_id=OWNER_ID),
            performance=ReservedPerformance(
                reserved_perf_id=PERF_ID,
                perf_starts_at=datetime(2026, 12, 1, 19, tzinfo=UTC),
                reserv_opens_at=datetime(2026, 11, 1, tzinfo=UTC),
                reserv_closes_at=datetime(2026, 11, 30, tzinfo=UTC),
            ),
            seat=ReservedSeat(reserved_seat_id=100, reserved_seat_price=Decimal("150000")),
            has_active_reservation=False,
            now=datetime(2026, 11, 5, tzinfo=UTC),
        )
        self.assertIsNone(reservation.reserv_id)

        # 실행
        saved = await self.repository.reserv_add(reservation)

        # 확인 : DB가 만든 값이 엔티티에 채워졌다
        self.assertIsNotNone(saved.reserv_id)
        self.assertIsNotNone(saved.created_at)

        # 확인 : DB에 실제로 들어갔다
        row = self.db.get(ReservationModel, saved.reserv_id)
        self.assertEqual(row.user_id, OWNER_ID)
        self.assertEqual(row.perf_id, PERF_ID)
        self.assertEqual(row.status, "PENDING")               # enum → DB 문자열
        self.assertEqual(row.total_amount, Decimal("150000"))

    # =========================================================
    # 2) find_by_reserv_id : 예매 ID로 찾기
    # =========================================================
    async def test_좌석과_결제가_연결된_예매를_찾는다(self):
        self.insert_reservation(reserv_id=5)
        self.link_seat_and_payment(reserv_id=5, perf_seat_id=100, pay_id=30)

        reservation = await self.repository.find_by_reserv_id(5)

        self.assertEqual(reservation.reserv_id, 5)
        self.assertEqual(reservation.status, ReservationStatus.CONFIRMED)    # DB 문자열 → enum
        self.assertEqual(reservation.ticketholder.ticketholder_id, OWNER_ID)
        self.assertEqual(reservation.performance.reserved_perf_id, PERF_ID)  # 회차 JOIN
        self.assertEqual(reservation.seat.reserved_seat_id, 100)             # 좌석 outerjoin
        self.assertEqual(reservation.seat.reserved_seat_price, Decimal("150000"))
        self.assertEqual(reservation.payment.reserved_pay_id, 30)            # 결제 outerjoin
        self.assertTrue(reservation.is_owned(OWNER_ID))                      # 엔티티 메서드 사용 가능

    async def test_좌석과_결제가_연결되지_않아도_예매는_찾는다(self):
        # outerjoin이라 연결이 없어도 예매는 나오고, 좌석·결제 ID만 None
        self.insert_reservation(reserv_id=6, status="CANCELED")

        reservation = await self.repository.find_by_reserv_id(6)

        self.assertIsNotNone(reservation)
        self.assertEqual(reservation.status, ReservationStatus.CANCELED)
        self.assertIsNone(reservation.seat.reserved_seat_id)
        self.assertIsNone(reservation.payment.reserved_pay_id)

    async def test_없는_예매_ID는_None을_돌려준다(self):
        reservation = await self.repository.find_by_reserv_id(999)

        self.assertIsNone(reservation)

    # =========================================================
    # 3) find_all_by_ticketholder : 회원의 예매 목록
    # =========================================================
    async def test_회원의_예매만_최신순으로_돌려준다(self):
        self.insert_reservation(reserv_id=1, created_at=datetime(2026, 11, 2, tzinfo=UTC))
        self.insert_reservation(reserv_id=2, created_at=datetime(2026, 11, 4, tzinfo=UTC))
        self.insert_reservation(reserv_id=3, created_at=datetime(2026, 11, 3, tzinfo=UTC))
        self.insert_reservation(reserv_id=4, user_id=OTHER_ID)    # 다른 회원 예매

        reservations = await self.repository.find_all_by_ticketholder(OWNER_ID)

        # 다른 회원 예매(4번)는 빠지고, 최신(created_at 큰 것)부터
        self.assertEqual([r.reserv_id for r in reservations], [2, 3, 1])

    async def test_예매가_없는_회원은_빈_리스트를_돌려준다(self):
        reservations = await self.repository.find_all_by_ticketholder(OWNER_ID)

        self.assertEqual(reservations, [])

    # =========================================================
    # 4) reserv_status_update : 바뀐 상태(확정, 취소) 저장
    # =========================================================
    async def test_확정하면_상태와_확정일시가_저장된다(self):
        # 준비 : 예매대기 예매를 조회해서 결제 성공 후 확정
        self.insert_reservation(reserv_id=5, status="PENDING", confirmed=False)
        reservation = await self.repository.find_by_reserv_id(5)
        confirm_time = datetime(2026, 11, 5, 0, 5)    # SQLite는 타임존을 버리므로 타임존 없이
        reservation.confirm(ReservedPayment(reserved_pay_id=30), confirm_time)

        # 실행
        await self.repository.reserv_status_update(reservation)

        # 확인 : DB 행이 바뀌었다
        row = self.db.get(ReservationModel, 5)
        self.assertEqual(row.status, "CONFIRMED")
        self.assertEqual(row.confirmed_at, confirm_time)
        self.assertIsNone(row.canceled_at)


    async def test_취소하면_상태와_취소일시가_저장되고_확정일시는_그대로다(self):
        # 준비 : 확정 예매를 조회해서 엔티티로 취소 (취소 일시는 cancel()이 정함)
        
        self.insert_reservation(reserv_id=5, created_at=datetime(2026, 11, 5, tzinfo=UTC))
        reservation = await self.repository.find_by_reserv_id(5)
        cancel_time = datetime(2026, 11, 20, 15)    # SQLite는 타임존을 버리므로 타임존 없이
        reservation.cancel(OWNER_ID, cancel_time)

        # 실행
        await self.repository.reserv_status_update(reservation)

        # 확인 : DB 행이 바뀌었다
        row = self.db.get(ReservationModel, 5)
        self.assertEqual(row.status, "CANCELED")                         # enum → DB 문자열
        self.assertEqual(row.canceled_at, cancel_time)                   # 취소한 시각 (created_at 아님)
        self.assertEqual(row.confirmed_at, datetime(2026, 11, 5))        # 확정 일시는 그대로

    async def test_없는_예매를_저장하면_LookupError(self):
        self.insert_reservation(reserv_id=5)
        reservation = await self.repository.find_by_reserv_id(5)
        reservation.reserv_id = 999                                      # DB에 없는 예매 ID

        with self.assertRaises(LookupError):
            await self.repository.reserv_status_update(reservation)


if __name__ == "__main__":
    unittest.main()
