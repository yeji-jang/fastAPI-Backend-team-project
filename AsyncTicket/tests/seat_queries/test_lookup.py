"""예매용 좌석 ID 조회의 회차 격리·가격·상태 보존 검사."""

from sqlalchemy import insert, select

from asyncticket.seats.application.service import PerformanceSeatService
from asyncticket.seats.infrastructure.models import PerformanceSeats, SeatsInfoModel
from asyncticket.seats.infrastructure.repositories import (
    SqlAlchemyPerformanceSeatRepository,
    SqlAlchemySeatInfoRepository,
)
from asyncticket.shared.core.exceptions import NotFoundException


class SeatIdLookupCases:
    async def test_id_lookup_scopes_performance_and_preserves_link(self):
        async with self.sessions() as session:
            await session.execute(
                insert(SeatsInfoModel).values(
                    seat_id=904,
                    perf_id=10,
                    name="R석",
                    total_seat=1,
                    price=0,
                )
            )
            await session.execute(
                insert(PerformanceSeats).values(
                    perf_seat_id=9004,
                    seat_id2=904,
                    reserv_id=1,
                    status="RESERVED",
                    seat_seq="LOOKUP/01",
                )
            )
            await session.commit()
            service = PerformanceSeatService(
                SqlAlchemyPerformanceSeatRepository(session),
                SqlAlchemySeatInfoRepository(session),
            )
            seat = await service.get_performance_seat_by_id(
                perf_id=10, perf_seat_id=9004
            )
            self.assertEqual(
                (seat["perf_seat_id"], seat["perf_id"], seat["price"], seat["status"]),
                (9004, 10, 0, "RESERVED"),
            )
            self.assertIs(type(seat["price"]), int)
            for perf_id, seat_id, code in (
                (20, 9004, "SEAT_NOT_FOUND"),
                (10, 9999, "SEAT_NOT_FOUND"),
                (9999, 9004, "PERFORMANCE_NOT_FOUND"),
            ):
                with self.subTest(perf_id=perf_id, seat_id=seat_id):
                    with self.assertRaises(NotFoundException) as caught:
                        await service.get_performance_seat_by_id(
                            perf_id=perf_id, perf_seat_id=seat_id
                        )
                    self.assertEqual(caught.exception.error_code, code)
            row = (
                await session.execute(
                    select(
                        PerformanceSeats.reserv_id,
                        PerformanceSeats.status,
                    ).where(PerformanceSeats.perf_seat_id == 9004)
                )
            ).one()
            self.assertEqual(tuple(row), (1, "RESERVED"))


import unittest
import test_queries


class SeatLookupTests(SeatIdLookupCases, unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_queries.SeatQueryTests.asyncSetUp
    asyncTearDown = test_queries.SeatQueryTests.asyncTearDown
