import unittest
from unittest.mock import AsyncMock
from asyncticket.seats.application.service import (
    PerformanceSeatService,
    SeatReservationConflictError,
)
from asyncticket.seats.domain.repository import PerformanceSeatRepository
from asyncticket.shared.core.exceptions import ValidationException


class SeatReleaseServiceTests(unittest.IsolatedAsyncioTestCase):
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

    def assert_no_transaction(self):
        self.assertTrue(
            all(
                call[0] == "release_reservation"
                for call in self.repository.method_calls
            )
        )

    async def test_release_forwards_caller_states_without_transaction(self):
        self.repository.release_reservation.return_value = True
        self.assertIsNone(await self.service.release_reservation(**self.values))
        self.repository.release_reservation.assert_awaited_once_with(**self.values)
        self.assert_no_transaction()

    async def test_release_conflict_does_not_own_transaction(self):
        self.repository.release_reservation.return_value = False
        with self.assertRaises(SeatReservationConflictError) as caught:
            await self.service.release_reservation(**self.values)
        self.assertEqual(caught.exception.error_code, "SEAT_RESERVATION_CONFLICT")
        self.assert_no_transaction()

    async def test_invalid_release_does_not_reach_repository(self):
        invalid = [
            ({name: value}, "INVALID_SEAT_RESERVATION_ID")
            for name in ("perf_id", "perf_seat_id", "reserv_id")
            for value in (0, -1)
        ]
        invalid += [
            (
                {"expected_status": before, "released_status": after},
                "INVALID_SEAT_STATUS_TRANSITION",
            )
            for before, after in (
                ("", "test-free"),
                ("test-linked", ""),
                ("same", "same"),
            )
        ]
        for override, code in invalid:
            with self.subTest(override=override):
                with self.assertRaises(ValidationException) as caught:
                    await self.service.release_reservation(
                        **{**self.values, **override}
                    )
                self.assertEqual(caught.exception.error_code, code)
        self.repository.release_reservation.assert_not_called()
        self.assert_no_transaction()
