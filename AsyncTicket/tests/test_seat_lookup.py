import unittest
from unittest.mock import AsyncMock
from asyncticket.seats.application.service import (
    PerformanceSeatService,
    SeatReservationConflictError,
)
from asyncticket.seats.domain.repository import PerformanceSeatRepository
from asyncticket.shared.core.exceptions import ValidationException


class SeatLookupServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.repository = AsyncMock(spec=PerformanceSeatRepository)
        self.service = PerformanceSeatService(self.repository, AsyncMock())
        self.values = dict(
            perf_id=1,
            perf_seat_id=2,
            reserv_id=3,
            expected_status="test-linked",
            released_status="test-free",
        )

    async def test_invalid_lookup_ids_do_not_reach_repositories(self):
        self.service.seat_info_repository = AsyncMock()
        for name in ("perf_id", "perf_seat_id"):
            for value in (0, -1, True, "1", None, 9223372036854775808):
                with self.subTest(name=name, value=value):
                    args = {"perf_id": 1, "perf_seat_id": 2, name: value}
                    with self.assertRaises(ValidationException):
                        await self.service.get_performance_seat_by_id(**args)
        self.repository.get_performance_seat_by_id.assert_not_called()
        self.service.seat_info_repository.performance_exists.assert_not_called()
