"""
예매 응용 서비스(application/service.py)와 좌석 배정 어댑터를 DB 없이 확인

<테스트 읽는 법>
- 응용 서비스는 순서만 조율하므로, 저장소·Reader·좌석 배정을 "가짜(Fake)"로 넣어서 확인한다
  (domain의 약속과 ports.py 덕분에 실제 DB·좌석 서비스 없이 갈아 끼울 수 있다)
- 1) 준비 : 가짜 부품에 필요한 데이터를 넣는다
  2) 실행 : 서비스 메서드를 호출한다
  3) 확인 : 결과 / 팀 공통 예외(HTTP 상태 코드, error_code) / 가짜 부품이 호출되었는지를 assert로 비교한다
- 실패하면 저장·좌석 호출이 일어나지 않는지도 함께 확인한다

<실행 방법> (AsyncTicket 폴더에서)
    .venv\\Scripts\\python -m unittest tests.test_reservation_application -v
"""

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from asyncticket.reservations.application.service import ReservationService
from asyncticket.reservations.domain.enums import ReservationStatus
from asyncticket.reservations.domain.reservation import (
    Reservation, TicketHolder, ReservedPerformance, ReservedSeat, ReservedPayment, ReservationError,
)
from asyncticket.reservations.infrastructure.adapter_seat_allocation import SeatAllocationAdapter

from asyncticket.reservations.presentation.exception_handlers import to_shared_exception

from asyncticket.seats.domain.enums import SeatStatus

UTC = timezone.utc
OPENS_AT = datetime(2026, 11, 1, tzinfo=UTC)
CLOSES_AT = datetime(2026, 11, 30, tzinfo=UTC)
STARTS_AT = datetime(2026, 12, 1, 19, tzinfo=UTC)
NOW = datetime(2026, 11, 5, tzinfo=UTC)          # 예매 기간 안

PERF_ID = 10
PERF_SEAT_ID = 100
OWNER_ID = 1
OTHER_ID = 2


# =========================================================
# 가짜 부품 (DB·좌석 서비스 대신 메모리에서 동작)
# =========================================================
class FakeRepository:
    """예매 저장소 대신 : 딕셔너리에 저장하고, 상태 저장 횟수를 기록"""

    def __init__(self):
        self.items: dict[int, Reservation] = {}
        self.next_id = 1
        self.status_updates = 0
        self.conflict = False   # True : "그 사이 다른 요청이 상태를 바꿔서" 저장이 실패하는 상황


    async def reserv_add(self, reservation):
        reservation.reserv_id = self.next_id
        reservation.created_at = NOW
        self.items[self.next_id] = reservation
        self.next_id += 1
        return reservation

    async def find_by_reserv_id(self, reserv_id):
        return self.items.get(reserv_id)

    async def find_all_by_ticketholder(self, ticketholder_id):
        return [r for r in self.items.values() if r.is_owned(ticketholder_id)]

    async def reserv_status_update(self, reservation, expected_status):
        if self.conflict:
            return False
        self.status_updates += 1
        return True


    async def find_pending_created_before(self, before):
        return [r for r in self.items.values()
                if r.status == ReservationStatus.PENDING and r.created_at <= before]


class FakeChecker:
    """1인 1건 확인 대신 : possible 값을 그대로 돌려줌"""

    def __init__(self, possible=True):
        self.possible = possible

    async def is_reserv_possible(self, ticketholder_id, perf_id):
        return self.possible


class FakePerformanceReader:
    """회차 Reader 대신 : PERF_ID 회차만 있음"""

    async def get_reserved_performance(self, perf_id):
        if perf_id != PERF_ID:
            return None
        return ReservedPerformance(
            reserved_perf_id=PERF_ID, perf_starts_at=STARTS_AT,
            reserv_opens_at=OPENS_AT, reserv_closes_at=CLOSES_AT,
        )


class FakeSeatReader:
    """좌석 Reader 대신 : PERF_ID 회차의 PERF_SEAT_ID 좌석만 있음"""

    async def get_reserved_seat(self, perf_id, perf_seat_id):
        if (perf_id, perf_seat_id) != (PERF_ID, PERF_SEAT_ID):
            return None
        return ReservedSeat(reserved_seat_id=PERF_SEAT_ID, reserved_seat_price=Decimal("150000"))


class FakeSeatAllocation:
    """좌석 배정(ports.py) 대신 : 잡기·놓기 호출을 기록"""

    def __init__(self):
        self.held = []
        self.released = []

    async def hold(self, **kwargs):
        self.held.append(kwargs)

    async def release(self, **kwargs):
        self.released.append(kwargs)


class ReservationServiceTests(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        """테스트마다 새 가짜 부품으로 서비스를 만든다"""
        self.repository = FakeRepository()
        self.checker = FakeChecker()
        self.seat_allocation = FakeSeatAllocation()
        self.service = ReservationService(
            repository=self.repository,
            checker=self.checker,
            performance_reader=FakePerformanceReader(),
            seat_reader=FakeSeatReader(),
            seat_allocation=self.seat_allocation,
        )

    async def store(self, *, status=ReservationStatus.CONFIRMED, owner_id=OWNER_ID, seat_id=PERF_SEAT_ID):
        """이미 저장된 예매를 가짜 저장소에 넣어 두는 도우미 (확정·취소·조회 테스트용)"""
        reservation = Reservation(
            ticketholder=TicketHolder(ticketholder_id=owner_id),
            performance=ReservedPerformance(
                reserved_perf_id=PERF_ID, perf_starts_at=STARTS_AT,
                reserv_opens_at=OPENS_AT, reserv_closes_at=CLOSES_AT,
            ),
            seat=ReservedSeat(reserved_seat_id=seat_id, reserved_seat_price=Decimal("150000")),
            order_number="ORD-TEST",
            total_amount=Decimal("150000"),
            status=status,
            confirmed_at=None if status == ReservationStatus.PENDING else NOW,
        )
        return await self.repository.reserv_add(reservation)

    def assert_error(self, error, status_code, error_code):
        """예매 도메인 예외의 error_code와, 표현 계층에서 바뀌는 HTTP 상태 코드 확인"""
        self.assertEqual(error.exception.error_code, error_code)
        self.assertEqual(to_shared_exception(error.exception).status_code, status_code)

    # =========================================================
    # 2. 예매하기 (reserve)
    # =========================================================
    async def test_예매하면_예매대기로_저장되고_좌석을_잡는다(self):
        reservation = await self.service.reserve(
            ticketholder_id=OWNER_ID, perf_id=PERF_ID, perf_seat_id=PERF_SEAT_ID, now=NOW,
        )

        self.assertEqual(reservation.status, ReservationStatus.PENDING)    # 결제 전이라 예매대기
        self.assertEqual(reservation.reserv_id, 1)                         # 저장 후 reserv_id 생김
        self.assertEqual(reservation.total_amount, Decimal("150000"))      # 금액 = 좌석 가격
        self.assertTrue(reservation.order_number.startswith("ORD-"))       # 토스 orderId로 쓸 주문번호
        self.assertEqual(self.seat_allocation.held, [                      # 저장한 reserv_id로 좌석 잡기
            {"perf_id": PERF_ID, "perf_seat_id": PERF_SEAT_ID, "reserv_id": 1},
        ])

    async def test_주문번호는_예매마다_다르다(self):
        first = await self.service.reserve(ticketholder_id=OWNER_ID, perf_id=PERF_ID, perf_seat_id=PERF_SEAT_ID, now=NOW)
        second = await self.service.reserve(ticketholder_id=OTHER_ID, perf_id=PERF_ID, perf_seat_id=PERF_SEAT_ID, now=NOW)

        self.assertNotEqual(first.order_number, second.order_number)

    async def test_이미_예매한_회차면_409(self):
        self.checker.possible = False

        with self.assertRaises(ReservationError) as error:
            await self.service.reserve(ticketholder_id=OWNER_ID, perf_id=PERF_ID, perf_seat_id=PERF_SEAT_ID, now=NOW)

        self.assert_error(error, 409, "RESERVATION_ALREADY_EXISTS")
        self.assertEqual(self.repository.items, {})          # 저장 안 됨
        self.assertEqual(self.seat_allocation.held, [])      # 좌석 안 잡음

    async def test_없는_회차면_404(self):
        with self.assertRaises(ReservationError) as error:
            await self.service.reserve(ticketholder_id=OWNER_ID, perf_id=999, perf_seat_id=PERF_SEAT_ID, now=NOW)

        self.assert_error(error, 404, "PERFORMANCE_NOT_FOUND")
        self.assertEqual(self.seat_allocation.held, [])

    async def test_없는_좌석이면_404(self):
        with self.assertRaises(ReservationError) as error:
            await self.service.reserve(ticketholder_id=OWNER_ID, perf_id=PERF_ID, perf_seat_id=999, now=NOW)

        self.assert_error(error, 404, "SEAT_NOT_FOUND")
        self.assertEqual(self.seat_allocation.held, [])

    async def test_예매_기간이_아니면_409(self):
        # 도메인 예외(ReservationConflictError) → 팀 공통 예외(409)로 바뀌는지 확인
        with self.assertRaises(ReservationError) as error:
            await self.service.reserve(ticketholder_id=OWNER_ID, perf_id=PERF_ID, perf_seat_id=PERF_SEAT_ID, now=CLOSES_AT)

        self.assert_error(error, 409, "RESERVATION_NOT_OPEN")
        self.assertEqual(self.repository.items, {})
        self.assertEqual(self.seat_allocation.held, [])

    # =========================================================
    # 3. 결제 후 확정 (confirm)
    # =========================================================
    async def test_결제_후_확정되고_상태가_저장된다(self):
        await self.store(status=ReservationStatus.PENDING)
        confirm_time = NOW + timedelta(minutes=3) # 결제 대기시간(5분 안에 확정)

        reservation = await self.service.confirm(reserv_id=1, pay_id=30, now=confirm_time)

        self.assertEqual(reservation.status, ReservationStatus.CONFIRMED)
        self.assertEqual(reservation.payment, ReservedPayment(reserved_pay_id=30))
        self.assertEqual(reservation.confirmed_at, confirm_time)
        self.assertEqual(self.repository.status_updates, 1)          # 상태 저장 호출

    async def test_없는_예매를_확정하면_404(self):
        with self.assertRaises(ReservationError) as error:
            await self.service.confirm(reserv_id=999, pay_id=30, now=NOW)

        self.assert_error(error, 404, "RESERVATION_NOT_FOUND")

    async def test_이미_확정된_예매를_다시_확정하면_409(self):
        await self.store(status=ReservationStatus.CONFIRMED)

        with self.assertRaises(ReservationError) as error:
            await self.service.confirm(reserv_id=1, pay_id=31, now=NOW)

        self.assert_error(error, 409, "RESERVATION_NOT_PENDING")
        self.assertEqual(self.repository.status_updates, 0)          # 저장 안 됨

    # =========================================================
    # 4. 예매 취소 (cancel)
    # =========================================================
    async def test_취소하면_상태를_저장하고_좌석을_놓는다(self):
        await self.store(status=ReservationStatus.CONFIRMED)
        cancel_time = NOW + timedelta(days=1)

        reservation = await self.service.cancel(reserv_id=1, ticketholder_id=OWNER_ID, now=cancel_time)

        self.assertEqual(reservation.status, ReservationStatus.CANCELED)
        self.assertEqual(reservation.canceled_at, cancel_time)
        self.assertEqual(self.repository.status_updates, 1)
        self.assertEqual(self.seat_allocation.released, [            # 예매에 있던 회차·좌석으로 놓기
            {"perf_id": PERF_ID, "perf_seat_id": PERF_SEAT_ID, "reserv_id": 1},
        ])

    async def test_다른_회원이_취소하면_403(self):
        await self.store(status=ReservationStatus.CONFIRMED)

        with self.assertRaises(ReservationError) as error:
            await self.service.cancel(reserv_id=1, ticketholder_id=OTHER_ID, now=NOW)

        self.assert_error(error, 403, "RESERVATION_FORBIDDEN")
        self.assertEqual(self.repository.status_updates, 0)
        self.assertEqual(self.seat_allocation.released, [])

    async def test_예매대기_상태는_취소하면_409(self):
        await self.store(status=ReservationStatus.PENDING)

        with self.assertRaises(ReservationError) as error:
            await self.service.cancel(reserv_id=1, ticketholder_id=OWNER_ID, now=NOW)

        self.assert_error(error, 409, "RESERVATION_NOT_CANCELABLE")
        self.assertEqual(self.seat_allocation.released, [])

    async def test_공연_시작_후_취소하면_409(self):
        await self.store(status=ReservationStatus.CONFIRMED)

        with self.assertRaises(ReservationError) as error:
            await self.service.cancel(reserv_id=1, ticketholder_id=OWNER_ID, now=STARTS_AT)

        self.assert_error(error, 409, "PERFORMANCE_ALREADY_STARTED")
        self.assertEqual(self.seat_allocation.released, [])

    async def test_좌석_연결이_없으면_좌석_놓기는_건너뛴다(self):
        # 저장소 outerjoin으로 좌석 ID가 None일 수 있음
        await self.store(status=ReservationStatus.CONFIRMED, seat_id=None)

        reservation = await self.service.cancel(reserv_id=1, ticketholder_id=OWNER_ID, now=NOW)

        self.assertEqual(reservation.status, ReservationStatus.CANCELED)
        self.assertEqual(self.seat_allocation.released, [])

    # =========================================================
    # 5. 예매 조회 (get_reservation, list_reservations)
    # =========================================================
    async def test_본인_예매를_조회한다(self):
        await self.store()

        reservation = await self.service.get_reservation(reserv_id=1, ticketholder_id=OWNER_ID)

        self.assertEqual(reservation.reserv_id, 1)

    async def test_다른_회원의_예매를_조회하면_403(self):
        await self.store()

        with self.assertRaises(ReservationError) as error:
            await self.service.get_reservation(reserv_id=1, ticketholder_id=OTHER_ID)

        self.assert_error(error, 403, "RESERVATION_FORBIDDEN")

    async def test_없는_예매를_조회하면_404(self):
        with self.assertRaises(ReservationError) as error:
            await self.service.get_reservation(reserv_id=999, ticketholder_id=OWNER_ID)

        self.assert_error(error, 404, "RESERVATION_NOT_FOUND")

    async def test_내_예매_목록만_돌려준다(self):
        await self.store(owner_id=OWNER_ID)
        await self.store(owner_id=OTHER_ID)
        await self.store(owner_id=OWNER_ID)

        reservations = await self.service.list_reservations(ticketholder_id=OWNER_ID)

        self.assertEqual([r.reserv_id for r in reservations], [1, 3])

    async def test_예매가_없으면_빈_리스트(self):
        # 목록의 빈 결과는 404가 아니라 정상 응답
        self.assertEqual(await self.service.list_reservations(ticketholder_id=OWNER_ID), [])

    # =========================================================
    # 6. 예매대기 만료 (find_expired_pending, expire)
    # =========================================================
    async def test_시간이_지난_예매대기를_만료_대상으로_찾는다(self):
        await self.store(status=ReservationStatus.PENDING)     # 1번 : NOW에 생성
        await self.store(status=ReservationStatus.CONFIRMED)   # 2번 : 확정은 대상 아님

        self.assertEqual(await self.service.find_expired_pending(now=NOW + timedelta(minutes=5)), [1])
        self.assertEqual(await self.service.find_expired_pending(now=NOW + timedelta(minutes=5, seconds=-1)), [])

    async def test_시간이_지난_예매대기는_만료되고_좌석을_놓는다(self):
        await self.store(status=ReservationStatus.PENDING)    # NOW에 생성

        expired = await self.service.expire(reserv_id=1, now=NOW + timedelta(minutes=5))

        self.assertTrue(expired)
        self.assertEqual(self.repository.items[1].status, ReservationStatus.EXPIRED)
        self.assertEqual(self.repository.status_updates, 1)          # 상태 저장 호출
        self.assertEqual(self.seat_allocation.released, [            # 잡고 있던 좌석 놓기
            {"perf_id": PERF_ID, "perf_seat_id": PERF_SEAT_ID, "reserv_id": 1},
        ])

    async def test_시간이_지나지_않은_예매대기는_그대로다(self):
        await self.store(status=ReservationStatus.PENDING)

        expired = await self.service.expire(reserv_id=1, now=NOW + timedelta(minutes=5, seconds=-1))

        self.assertFalse(expired)
        self.assertEqual(self.repository.items[1].status, ReservationStatus.PENDING)
        self.assertEqual(self.repository.status_updates, 0)          # 저장 안 됨
        self.assertEqual(self.seat_allocation.released, [])          # 좌석 그대로

    async def test_대상을_찾은_뒤_확정된_예매는_만료하지_않는다(self):
        # 목록을 찾은 뒤 다시 조회했을 때 이미 확정이면 건너뛴다
        await self.store(status=ReservationStatus.CONFIRMED)

        expired = await self.service.expire(reserv_id=1, now=NOW + timedelta(days=1))

        self.assertFalse(expired)
        self.assertEqual(self.repository.items[1].status, ReservationStatus.CONFIRMED)
        self.assertEqual(self.seat_allocation.released, [])

    async def test_만료된_예매를_확정하면_409(self):
        await self.store(status=ReservationStatus.PENDING)
        await self.service.expire(reserv_id=1, now=NOW + timedelta(minutes=5))

        with self.assertRaises(ReservationError) as error:
            await self.service.confirm(reserv_id=1, pay_id=30, now=NOW + timedelta(minutes=6))

        self.assert_error(error, 409, "RESERVATION_NOT_PENDING")

    async def test_만료_처리_전이라도_시간이_지나면_확정하면_409(self):
        # 만료 처리가 아직 안 돌아서 PENDING이어도 5분이 지났으면 확정 불가
        await self.store(status=ReservationStatus.PENDING)

        with self.assertRaises(ReservationError) as error:
            await self.service.confirm(reserv_id=1, pay_id=30, now=NOW + timedelta(minutes=5))

        self.assert_error(error, 409, "RESERVATION_EXPIRED")
        self.assertEqual(self.repository.status_updates, 0)          # 저장 안 됨

    # =========================================================
    # 7. 동시 요청 (저장 직전에 다른 요청이 상태를 바꾼 경우)
    # =========================================================
    async def test_확정_저장_전에_만료되었으면_409(self):
        await self.store(status=ReservationStatus.PENDING)
        self.repository.conflict = True                              # 그 사이 만료 작업이 먼저 저장

        with self.assertRaises(ReservationError) as error:
            await self.service.confirm(reserv_id=1, pay_id=30, now=NOW + timedelta(minutes=3))

        self.assert_error(error, 409, "RESERVATION_NOT_PENDING")

    async def test_취소_저장_전에_이미_취소되었으면_409이고_좌석을_놓지_않는다(self):
        await self.store(status=ReservationStatus.CONFIRMED)
        self.repository.conflict = True                              # 그 사이 다른 취소 요청이 먼저 저장

        with self.assertRaises(ReservationError) as error:
            await self.service.cancel(reserv_id=1, ticketholder_id=OWNER_ID, now=NOW)

        self.assert_error(error, 409, "RESERVATION_NOT_CANCELABLE")
        self.assertEqual(self.seat_allocation.released, [])          # 좌석 두 번 해제 방지

    async def test_만료_저장_전에_확정되었으면_건너뛰고_좌석을_놓지_않는다(self):
        await self.store(status=ReservationStatus.PENDING)
        self.repository.conflict = True                              # 그 사이 확정 요청이 먼저 저장

        expired = await self.service.expire(reserv_id=1, now=NOW + timedelta(minutes=5))

        self.assertFalse(expired)                                    # 만료 안 됨
        self.assertEqual(self.seat_allocation.released, [])          # 결제한 사람의 좌석은 그대로



class FakeSeatService:
    """좌석 서비스(PerformanceSeatService) 대신 : 받은 인자를 기록"""

    def __init__(self):
        self.assigned = None
        self.released = None

    async def assign_reservation(self, **kwargs):
        self.assigned = kwargs

    async def release_reservation(self, **kwargs):
        self.released = kwargs


class SeatAllocationAdapterTests(unittest.IsolatedAsyncioTestCase):
    """좌석 배정 어댑터 : 잡기·놓기를 좌석 서비스 호출 + SeatStatus로 바꾸는지 확인"""

    def setUp(self):
        self.seat_service = FakeSeatService()
        self.adapter = SeatAllocationAdapter(self.seat_service)

    async def test_잡기는_AVAILABLE에서_RESERVED로_연결한다(self):
        await self.adapter.hold(perf_id=PERF_ID, perf_seat_id=PERF_SEAT_ID, reserv_id=5)

        self.assertEqual(self.seat_service.assigned, {
            "perf_id": PERF_ID, "perf_seat_id": PERF_SEAT_ID, "reserv_id": 5,
            "expected_status": SeatStatus.AVAILABLE, "reserved_status": SeatStatus.RESERVED,
        })

    async def test_놓기는_RESERVED에서_AVAILABLE로_해제한다(self):
        await self.adapter.release(perf_id=PERF_ID, perf_seat_id=PERF_SEAT_ID, reserv_id=5)

        self.assertEqual(self.seat_service.released, {
            "perf_id": PERF_ID, "perf_seat_id": PERF_SEAT_ID, "reserv_id": 5,
            "expected_status": SeatStatus.RESERVED, "released_status": SeatStatus.AVAILABLE,
        })

    

if __name__ == "__main__":
    unittest.main()
