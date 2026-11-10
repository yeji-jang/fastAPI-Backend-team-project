"""
예매대기 만료 작업(wiring/reservations.py의 expire_pending_reservations)을 DB 없이 확인

<확인하는 것>
- 예매마다 트랜잭션(세션)을 따로 연다
- 한 건의 좌석 해제가 실패해도 그 건만 rollback 하고, 나머지 예매는 만료·commit 된다

<실행 방법> (AsyncTicket 폴더에서)
    .venv\\Scripts\\python -m unittest discover -s tests/reservations
"""

import unittest
from datetime import timedelta

import test_reservation_application as app_tests    # 서비스 테스트의 가짜 부품 재사용

from asyncticket.reservations.application.service import ReservationService
from asyncticket.reservations.domain.enums import ReservationStatus
from asyncticket.wiring.reservations import expire_pending_reservations

EXPIRED_TIME = app_tests.NOW + timedelta(minutes=5)     # 생성 후 5분 (만료 시각)


class FakeSession:
    """DB 세션 대신 : commit / rollback 호출 순서만 기록"""

    def __init__(self, log):
        self.log = log

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        self.log.append("commit")

    async def rollback(self):
        self.log.append("rollback")


class BrokenSeatAllocation(app_tests.FakeSeatAllocation):
    """좌석 배정 대신 : 지정한 예매의 좌석 해제만 실패 (좌석이 RESERVED가 아닌 상황 등)"""

    def __init__(self, broken_reserv_id):
        super().__init__()
        self.broken_reserv_id = broken_reserv_id

    async def release(self, **kwargs):
        if kwargs["reserv_id"] == self.broken_reserv_id:
            raise RuntimeError("좌석 해제 실패")
        await super().release(**kwargs)


class ExpiryJobTests(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.log = []
        self.repository = app_tests.FakeRepository()
        self.seat_allocation = BrokenSeatAllocation(broken_reserv_id=1)   # 1번 예매만 좌석 해제 실패

    def session_factory(self):
        return FakeSession(self.log)

    def service_factory(self, session):
        return ReservationService(
            repository=self.repository,
            checker=app_tests.FakeChecker(),
            performance_reader=app_tests.FakePerformanceReader(),
            seat_reader=app_tests.FakeSeatReader(),
            seat_allocation=self.seat_allocation,
            payment_refund=app_tests.FakePaymentRefund(), # 예매 만료에서는 환불 안함
        )

    async def run_job(self):
        return await expire_pending_reservations(
            now=EXPIRED_TIME,
            session_factory=self.session_factory,
            service_factory=self.service_factory,
        )

    async def test_한_건의_좌석_해제가_실패해도_나머지는_만료된다(self):
        # 준비 : 만료 대상 예매대기 2건 (1번은 좌석 해제가 실패하는 예매)
        service = self.service_factory(None)
        await service.reserve(ticketholder_id=app_tests.OWNER_ID, perf_id=app_tests.PERF_ID,
                              perf_seat_id=app_tests.PERF_SEAT_ID, now=app_tests.NOW)   # 1번
        await service.reserve(ticketholder_id=app_tests.OTHER_ID, perf_id=app_tests.PERF_ID,
                              perf_seat_id=app_tests.PERF_SEAT_ID, now=app_tests.NOW)   # 2번

        # 실행
        expired_count = await self.run_job()

        # 확인 : 1번은 rollback, 2번은 만료 후 commit
        self.assertEqual(expired_count, 1)
        self.assertEqual(self.log, ["rollback", "commit"])
        self.assertEqual(self.repository.items[2].status, ReservationStatus.EXPIRED)
        self.assertEqual(self.seat_allocation.released, [
            {"perf_id": app_tests.PERF_ID, "perf_seat_id": app_tests.PERF_SEAT_ID, "reserv_id": 2},
        ])

    async def test_만료_대상이_없으면_아무것도_하지_않는다(self):
        expired_count = await self.run_job()

        self.assertEqual(expired_count, 0)
        self.assertEqual(self.log, [])                  # 예매별 트랜잭션을 열지 않음
