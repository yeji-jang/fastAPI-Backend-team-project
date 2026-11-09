"""잘못 저장된 데이터가 사용자 입력 오류로 전달되지 않는지 확인한다."""

import unittest

from asyncticket.seats.infrastructure.models import SeatsInfoModel, PerformanceSeats
from asyncticket.shared.core.exceptions import ValidationException


class SeatMappingTests(unittest.TestCase):
    def test_invalid_stored_grade_is_not_request_validation(self):
        for field, value in [("price", -1), ("total_seat", 0), ("perf_id", 0)]:
            values = dict(seat_id=1, perf_id=1, name="R석", total_seat=1, price=0)
            values[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError) as caught:
                SeatsInfoModel(**values).to_seat_info()
            self.assertIsInstance(caught.exception.__cause__, ValidationException)

    def test_invalid_stored_seat_is_not_request_validation(self):
        for field, value in [("seat_seq", " "), ("seat_id2", 0), ("reserv_id", 0)]:
            values = dict(
                perf_seat_id=1,
                seat_id2=1,
                reserv_id=None,
                status="AVAILABLE",
                seat_seq="A1",
            )
            values[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError) as caught:
                PerformanceSeats(**values).to_performance_seat()
            self.assertIsInstance(caught.exception.__cause__, ValidationException)

    def test_valid_free_seat_grade_still_restores(self):
        grade = SeatsInfoModel(
            seat_id=1, perf_id=1, name="R석", total_seat=1, price=0
        ).to_seat_info()
        self.assertEqual(grade.price, 0)
