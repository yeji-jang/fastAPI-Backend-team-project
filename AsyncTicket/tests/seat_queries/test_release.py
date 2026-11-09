"""SQLite·PostgreSQL에서 함께 확인하는 좌석 연결 해제 시나리오."""

from sqlalchemy import insert, select, text

from asyncticket.seats.application.service import (
    PerformanceSeatService,
    SeatReservationConflictError,
)
from asyncticket.seats.infrastructure.models import PerformanceSeats, SeatsInfoModel
from asyncticket.seats.infrastructure.repositories import (
    SqlAlchemyPerformanceSeatRepository,
    SqlAlchemySeatInfoRepository,
)


class SeatReleaseCases:
    async def test_release_rejects_reservation_from_another_performance(self):
        async with self.sessions() as session:
            await session.execute(
                insert(SeatsInfoModel).values(
                    seat_id=903,
                    perf_id=10,
                    name="R석",
                    total_seat=1,
                    price=100,
                )
            )
            # FK만으로 막을 수 없는 회차 불일치를 만들고 EXISTS 조건을 독립 검사한다.
            await session.execute(
                insert(PerformanceSeats).values(
                    perf_seat_id=9003,
                    seat_id2=903,
                    reserv_id=2,
                    status="TEST_LINKED",
                    seat_seq="RELEASE/03",
                )
            )
            await session.commit()
            service = PerformanceSeatService(
                SqlAlchemyPerformanceSeatRepository(session),
                SqlAlchemySeatInfoRepository(session),
            )
            with self.assertRaises(SeatReservationConflictError):
                await service.release_reservation(
                    perf_id=10,
                    perf_seat_id=9003,
                    reserv_id=2,
                    expected_status="TEST_LINKED",
                    released_status="TEST_FREE",
                )
            row = (
                await session.execute(
                    select(
                        PerformanceSeats.reserv_id,
                        PerformanceSeats.status,
                    ).where(PerformanceSeats.perf_seat_id == 9003)
                )
            ).one()
            self.assertEqual(tuple(row), (2, "TEST_LINKED"))

    async def test_release_guards_rollback_and_caller_commit(self):
        async with self.sessions() as session:
            await session.execute(
                insert(SeatsInfoModel).values(
                    seat_id=901,
                    perf_id=10,
                    name="R석",
                    total_seat=1,
                    price=0,
                )
            )
            await session.execute(
                insert(PerformanceSeats).values(
                    perf_seat_id=9001,
                    seat_id2=901,
                    reserv_id=1,
                    status="TEST_LINKED",
                    seat_seq="RELEASE/01",
                )
            )
            await session.commit()
            service = PerformanceSeatService(
                SqlAlchemyPerformanceSeatRepository(session),
                SqlAlchemySeatInfoRepository(session),
            )
            args = dict(
                perf_id=10,
                perf_seat_id=9001,
                reserv_id=1,
                expected_status="TEST_LINKED",
                released_status="TEST_FREE",
            )

            async def state():
                return tuple(
                    (
                        await session.execute(
                            select(
                                PerformanceSeats.reserv_id,
                                PerformanceSeats.status,
                            ).where(PerformanceSeats.perf_seat_id == 9001)
                        )
                    ).one()
                )

            for override in (
                {"perf_id": 20},
                {"perf_seat_id": 9999},
                {"reserv_id": 2},
                {"reserv_id": 999},
                {"expected_status": "WRONG"},
            ):
                with self.subTest(override=override):
                    with self.assertRaises(SeatReservationConflictError):
                        await service.release_reservation(**{**args, **override})
                    self.assertEqual(await state(), (1, "TEST_LINKED"))

            await service.release_reservation(**args)
            self.assertEqual(await state(), (None, "TEST_FREE"))
            with self.assertRaises(SeatReservationConflictError):
                await service.release_reservation(**args)
            await session.rollback()
            self.assertEqual(await state(), (1, "TEST_LINKED"))

            await service.release_reservation(**args)
            await session.commit()

        async with self.sessions() as session:
            row = (
                await session.execute(
                    select(
                        PerformanceSeats.reserv_id,
                        PerformanceSeats.status,
                    ).where(PerformanceSeats.perf_seat_id == 9001)
                )
            ).one()
            self.assertEqual(tuple(row), (None, "TEST_FREE"))

    async def test_previous_reservation_cannot_release_reassigned_seat(self):
        async with self.sessions() as session:
            # 같은 회차의 새 예매는 좌석 검사만을 위한 부모 픽스처다.
            await session.execute(
                text("INSERT INTO reservations (reserv_id, perf_id) VALUES (3, 10)")
            )
            await session.execute(
                insert(SeatsInfoModel).values(
                    seat_id=902,
                    perf_id=10,
                    name="S석",
                    total_seat=1,
                    price=100,
                )
            )
            await session.execute(
                insert(PerformanceSeats).values(
                    perf_seat_id=9002,
                    seat_id2=902,
                    reserv_id=1,
                    status="TEST_LINKED",
                    seat_seq="RELEASE/02",
                )
            )
            await session.commit()
            service = PerformanceSeatService(
                SqlAlchemyPerformanceSeatRepository(session),
                SqlAlchemySeatInfoRepository(session),
            )
            args = dict(
                perf_id=10,
                perf_seat_id=9002,
                reserv_id=1,
                expected_status="TEST_LINKED",
                released_status="TEST_FREE",
            )
            await service.release_reservation(**args)
            await service.assign_reservation(
                perf_id=10,
                perf_seat_id=9002,
                reserv_id=3,
                expected_status="TEST_FREE",
                reserved_status="TEST_LINKED",
            )
            await session.commit()
            with self.assertRaises(SeatReservationConflictError):
                await service.release_reservation(**args)
            row = (
                await session.execute(
                    select(
                        PerformanceSeats.reserv_id,
                        PerformanceSeats.status,
                    ).where(PerformanceSeats.perf_seat_id == 9002)
                )
            ).one()
            self.assertEqual(tuple(row), (3, "TEST_LINKED"))


import unittest
import test_queries


class SeatReleaseTests(SeatReleaseCases, unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_queries.SeatQueryTests.asyncSetUp
    asyncTearDown = test_queries.SeatQueryTests.asyncTearDown
