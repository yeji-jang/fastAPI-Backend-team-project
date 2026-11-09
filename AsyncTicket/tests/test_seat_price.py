"""가격 변경 실패가 저장·확정으로 이어지지 않는지 확인한다."""

from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import AsyncMock

from asyncticket.seats.application.service import SeatInfoService
from asyncticket.seats.domain.enums import SeatGrade
from asyncticket.seats.domain.repository import (
    SeatInfoRepository,
    PerformanceSeatRepository,
)
from asyncticket.seats.domain.seat_info import SeatInfo, SeatInfoNotFoundError
from asyncticket.shared.core.exceptions import ValidationException
from asyncticket.shared.domain.catalog import CatalogActor, CatalogPolicy


class SeatPriceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.repository = AsyncMock(spec=SeatInfoRepository)
        self.repository.lock_performance.return_value = True
        self.repository.get_management_context.return_value = {
            "owner_id": 7,
            "booking_opens_at": datetime.now(timezone.utc) + timedelta(days=1),
        }
        self.grade = SeatInfo(
            seat_id=101, perf_id=10, name=SeatGrade.R, total_seat=2, price=100
        )
        self.repository.get_seat_info.return_value = self.grade
        self.service = SeatInfoService(
            self.repository,
            AsyncMock(spec=PerformanceSeatRepository),
            CatalogPolicy(),
        )
        self.actor = CatalogActor(user_id=7, role="SELLER")

    async def test_save_failure_rolls_back_without_commit(self):
        self.repository.save_seat_info.side_effect = RuntimeError("save failed")
        with self.assertRaisesRegex(RuntimeError, "save failed"):
            await self.service.update_price(10, 101, 0, self.actor)
        self.repository.commit.assert_not_awaited()
        self.repository.rollback.assert_awaited_once()
        self.assertEqual(self.grade.price, 100)

    async def test_other_performance_grade_is_not_saved(self):
        self.repository.get_seat_info.return_value = SeatInfo(
            seat_id=101,
            perf_id=20,
            name=SeatGrade.R,
            total_seat=2,
            price=100,
        )
        with self.assertRaises(SeatInfoNotFoundError):
            await self.service.update_price(10, 101, 0, self.actor)
        self.repository.save_seat_info.assert_not_awaited()
        self.repository.commit.assert_not_awaited()
        self.repository.rollback.assert_awaited_once()

    async def test_invalid_price_is_domain_validation_without_save(self):
        with self.assertRaises(ValidationException) as caught:
            await self.service.update_price(10, 101, -1, self.actor)
        self.assertEqual(caught.exception.status_code, 422)
        self.assertEqual(caught.exception.error_code, "VALIDATION_ERROR")
        self.repository.save_seat_info.assert_not_awaited()
        self.repository.commit.assert_not_awaited()
        self.repository.rollback.assert_awaited_once()
