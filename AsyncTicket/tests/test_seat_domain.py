"""DB 없이 좌석 도메인의 정상·경계·실패 조건을 확인한다."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import unittest

from asyncticket.seats.domain.seat_info import (
    SeatInfo,
    SeatConfigurationConflictError,
    SeatManagement,
    SeatInfoNotFoundError,
)
from asyncticket.shared.core.exceptions import (
    ConflictException,
    SharedException,
    ValidationException,
)
from asyncticket.seats.domain.enums import SeatGrade, SeatStatus
from asyncticket.seats.domain.performance_seat import PerformanceSeat
from asyncticket.shared.domain.catalog import (
    CatalogActor,
    CatalogPolicy,
    CatalogForbiddenError,
)


class SeatInfoTests(unittest.TestCase):
    def setUp(self):
        self.grade = SeatInfo(
            seat_id=101, perf_id=10, name=SeatGrade.R, total_seat=30, price=55000
        )

    def test_remaining_seats(self):
        self.assertEqual(self.grade.remaining_seats(8), 22)

    def test_exact_remaining_quantity_is_allowed(self):
        self.assertIsNone(self.grade.require_capacity(22, 8))

    def test_insufficient_capacity_is_rejected_without_mutation(self):
        with self.assertRaisesRegex(ValidationException, "남은 좌석"):
            self.grade.require_capacity(23, 8)
        self.assertEqual(self.grade.remaining_seats(8), 22)

    def test_invalid_quantities(self):
        for quantity in (0, -1, True, "1"):
            with self.subTest(quantity=quantity):
                with self.assertRaises(ValidationException):
                    self.grade.require_capacity(quantity, 0)

    def test_invalid_occupied_counts(self):
        for count in (-1, 31, True, "8"):
            with self.subTest(count=count):
                with self.assertRaises(ValidationException):
                    self.grade.remaining_seats(count)

    def test_invalid_identifiers(self):
        for field in ("seat_id", "perf_id"):
            for value in (0, -1, True, "10"):
                with self.subTest(field=field, value=value):
                    values = dict(
                        seat_id=101,
                        perf_id=10,
                        name=SeatGrade.R,
                        total_seat=30,
                        price=55000,
                    )
                    values[field] = value
                    with self.assertRaises(ValidationException):
                        SeatInfo(**values)

    def test_invalid_capacity_or_price(self):
        for field in ("total_seat", "price"):
            for value in (-1, True, "100"):
                with self.subTest(field=field, value=value):
                    values = dict(
                        seat_id=101,
                        perf_id=10,
                        name=SeatGrade.R,
                        total_seat=30,
                        price=55000,
                    )
                    values[field] = value
                    with self.assertRaises(ValidationException):
                        SeatInfo(**values)

    def test_incomplete_configuration_is_rejected_at_creation(self):
        with self.assertRaises(TypeError):
            SeatInfo(seat_id=101, perf_id=10)

    def test_each_required_configuration_field(self):
        for field, value in (
            ("name", None),
            ("name", " "),
            ("total_seat", None),
            ("price", None),
        ):
            with self.subTest(field=field, value=value):
                values = dict(
                    seat_id=101,
                    perf_id=10,
                    name=SeatGrade.R,
                    total_seat=30,
                    price=55000,
                )
                values[field] = value
                with self.assertRaises(ValidationException):
                    SeatInfo(**values)

    def test_nonnegative_price_and_positive_capacity_boundaries(self):
        for field, value in (("total_seat", 0), ("price", -1)):
            with self.subTest(field=field, value=value):
                values = dict(
                    seat_id=101, perf_id=10, name=SeatGrade.R, total_seat=30, price=0
                )
                values[field] = value
                with self.assertRaises(ValidationException):
                    SeatInfo(**values)
        minimum = SeatInfo(
            seat_id=101, perf_id=10, name=SeatGrade.R, total_seat=1, price=0
        )
        for price in (0, 1, 49999):
            with self.subTest(price=price):
                grade = SeatInfo(
                    seat_id=101, perf_id=10, name=SeatGrade.R, total_seat=1, price=price
                )
                self.assertEqual(grade.price, price)
        self.assertEqual(minimum.remaining_seats(0), 1)
        self.assertEqual(minimum.remaining_seats(1), 0)
        with self.assertRaises(ValidationException):
            minimum.require_capacity(1, 1)

    def test_invalid_grade_name(self):
        for name in (False, 42, "가" * 256):
            with self.subTest(name=name):
                with self.assertRaises(ValidationException):
                    SeatInfo(
                        seat_id=101, perf_id=10, name=name, total_seat=30, price=55000
                    )

    def test_price_update_preserves_original_and_configuration(self):
        changed = self.grade.update_price(0)
        self.assertEqual(changed.price, 0)
        self.assertEqual(self.grade.price, 55000)
        self.assertEqual(replace(changed, price=self.grade.price), self.grade)

    def test_price_update_rejects_invalid_price_and_unsaved_grade(self):
        for price in (-1, True, "100"):
            with self.subTest(price=price), self.assertRaises(ValidationException):
                self.grade.update_price(price)
        with self.assertRaisesRegex(ValidationException, "신규 등급"):
            replace(self.grade, seat_id=None).update_price(100)

    def test_price_update_rejects_other_performance_without_mutation(self):
        with self.assertRaises(SeatInfoNotFoundError) as caught:
            self.grade.update_price(100, perf_id=20)
        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(caught.exception.error_code, "SEAT_INFO_NOT_FOUND")
        self.assertEqual(self.grade.price, 55000)
        self.assertEqual(self.grade.update_price(100, perf_id=10).price, 100)

    def test_existing_grade_or_seat_names_reject_configuration(self):
        for check in (
            self.grade.require_unique_grade,
            self.grade.require_unique_seat_names,
        ):
            self.assertIsNone(check(False))
            with self.assertRaises(SeatConfigurationConflictError):
                check(True)

    def test_new_configuration_rejects_saved_grade_and_duplicate_names(self):
        with self.assertRaisesRegex(ValidationException, "등급 ID"):
            self.grade.require_new_configuration(["A1"])
        grade = SeatInfo.create(perf_id=10, name=SeatGrade.R, total_seat=2, price=0)
        with self.assertRaisesRegex(ValidationException, "중복된 좌석명"):
            grade.require_new_configuration(["A1", "A1"])
        self.assertEqual(
            grade.require_new_configuration(["A1", "A2"]).values, ("A1", "A2")
        )

    def test_validated_seat_names_are_a_snapshot_and_check_saved_capacity(self):
        grade = SeatInfo.create(perf_id=10, name=SeatGrade.R, total_seat=2, price=0)
        source = ["A1", "A2"]
        names = grade.require_new_configuration(source)
        source[1] = "A1"
        seats = replace(grade, seat_id=101).create_seats(names)
        self.assertEqual([seat.seat_seq for seat in seats], ["A1", "A2"])
        with self.assertRaisesRegex(ValidationException, "좌석명 개수"):
            replace(grade, seat_id=101, total_seat=3).create_seats(names)
        with self.assertRaisesRegex(ValidationException, "중복된 좌석명"):
            replace(grade, seat_id=101).create_seats(source)

    def test_new_individual_seat_has_no_reservation_or_generated_id(self):
        seat = PerformanceSeat.create(
            seat_id=101, seat_seq="A1", status=SeatStatus.AVAILABLE
        )
        self.assertIsNone(seat.perf_seat_id)
        self.assertIsNone(seat.reserv_id)
        with self.assertRaisesRegex(ValidationException, "좌석명"):
            PerformanceSeat.create(
                seat_id=101, seat_seq=" ", status=SeatStatus.AVAILABLE
            )

    def test_management_checks_owner_before_sale_time(self):
        management = SeatManagement(owner_id=7, booking_opens_at=None)
        with self.assertRaises(CatalogForbiddenError):
            management.authorize_change(
                CatalogActor(user_id=8, role="SELLER"),
                CatalogPolicy(),
                now=datetime.now(timezone.utc),
            )
        with self.assertRaises(SharedException) as caught:
            management.authorize_change(
                CatalogActor(user_id=7, role="SELLER"),
                CatalogPolicy(),
                now=datetime.now(timezone.utc),
            )
        self.assertEqual(caught.exception.error_code, "INVALID_BOOKING_TIME")

    def test_management_allows_only_before_sale(self):
        now = datetime.now(timezone.utc)
        management = SeatManagement(owner_id=1, booking_opens_at=now)
        management.require_before_sale(now - timedelta(seconds=1))
        with self.assertRaises(ConflictException) as caught:
            management.require_before_sale(now)
        self.assertEqual(caught.exception.error_code, "SEAT_SALE_STARTED")

    def test_management_rejects_invalid_external_context(self):
        with self.assertRaises(SharedException) as caught:
            SeatManagement(owner_id=None, booking_opens_at=None)
        self.assertEqual(caught.exception.error_code, "INVALID_SHOW_OWNER")
        with self.assertRaises(SharedException) as caught:
            SeatManagement(owner_id=1, booking_opens_at=None).require_before_sale(
                datetime.now(timezone.utc)
            )
        self.assertEqual(caught.exception.error_code, "INVALID_BOOKING_TIME")

    def test_validated_values_cannot_be_changed_directly(self):
        with self.assertRaises(FrozenInstanceError):
            self.grade.total_seat = -1


if __name__ == "__main__":
    unittest.main()
