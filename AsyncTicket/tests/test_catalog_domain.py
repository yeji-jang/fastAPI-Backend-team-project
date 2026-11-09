"""Exercise catalog entity rules directly, without HTTP, ORM or a database."""

from dataclasses import FrozenInstanceError, asdict
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
import unittest

from asyncticket.performances.domain.performance import Performance
from asyncticket.shared.domain.catalog import CatalogPolicy, CatalogValidationError
from asyncticket.shows.domain.show import Show


KST = timezone(timedelta(hours=9))
T0 = datetime(2026, 11, 7, 19, tzinfo=KST)
POLICY = CatalogPolicy()


def show_values(**changes):
    values = dict(
        show_id=11, venues_id=2, user_id=3, title="A show", description="Details",
        performer="A performer", type="CONCERT", runtime=120,
        created_at=T0 - timedelta(days=10), updated_at=None,
    )
    return {**values, **changes}


def performance_values(**changes):
    values = dict(
        perf_id=21, show_id=11, round_number=1, starts_at=T0,
        ends_at=T0 + timedelta(hours=2), booking_opens_at=T0 - timedelta(days=7),
        booking_closes_at=T0 - timedelta(hours=1), max_tickets_per_user=3,
        status="SCHEDULED",
    )
    return {**values, **changes}


def show_creation_values(**changes):
    values = show_values(**changes)
    return {key: value for key, value in values.items()
            if key not in {"show_id", "user_id", "created_at", "updated_at"}}


def performance_creation_values(**changes):
    values = performance_values(**changes)
    return {key: value for key, value in values.items() if key not in {"perf_id", "show_id"}}


class ShowDomainTests(unittest.TestCase):
    def test_constructor_rejects_invalid_title_and_type(self):
        for field, value in (
            ("title", ""), ("title", "   "), ("title", "x" * 256), ("title", None),
            ("type", ""), ("type", "   "), ("type", "x" * 51), ("type", None),
        ):
            with self.subTest(field=field, value=value):
                with self.assertRaises(CatalogValidationError):
                    Show(**show_values(**{field: value}))

    def test_constructor_rejects_nonpositive_or_noninteger_runtime(self):
        for value in (0, -1, True, "120"):
            with self.subTest(value=value):
                with self.assertRaises(CatalogValidationError):
                    Show(**show_values(runtime=value))
        self.assertIsNone(Show(**show_values(runtime=None)).runtime)

    def test_constructor_preserves_values_and_unconfigured_type(self):
        values = show_values(title=" A show ", type="TEAM_CUSTOM_TYPE")
        show = Show(**values)
        self.assertEqual(asdict(show), values)
        self.assertIs(show.created_at.tzinfo, KST)

    def test_creation_validation_needs_no_generated_id_and_does_not_mutate_input(self):
        values = show_creation_values()
        before = dict(values)
        self.assertIsNone(Show.validate_creation(MappingProxyType(values), POLICY))
        self.assertEqual(values, before)
        self.assertNotIn("show_id", values)
        self.assertNotIn("user_id", values)
        self.assertNotIn("created_at", values)

    def test_creation_validation_rejects_bad_values_without_mutating_input(self):
        values = show_creation_values(runtime=-1)
        before = dict(values)
        with self.assertRaises(CatalogValidationError):
            Show.validate_creation(values, POLICY)
        self.assertEqual(values, before)

    def test_creation_validation_applies_explicit_type_allowlist(self):
        policy = CatalogPolicy(show_types=frozenset({"CLASS"}))
        with self.assertRaises(CatalogValidationError):
            Show.validate_creation(show_creation_values(type="CONCERT"), policy)
        self.assertIsNone(Show.validate_creation(show_creation_values(type="CLASS"), policy))

    def test_partial_change_returns_new_object_and_preserves_omitted_fields(self):
        show = Show(**show_values())
        before = asdict(show)
        changes = {"title": "Updated title", "venues_id": 4}
        changed = show.with_changes(MappingProxyType(changes), POLICY)
        self.assertIsNot(changed, show)
        self.assertEqual(asdict(show), before)
        self.assertEqual(asdict(changed), {**before, **changes})
        self.assertEqual(changes, {"title": "Updated title", "venues_id": 4})

    def test_nullable_changes_clear_values_without_changing_the_original(self):
        show = Show(**show_values())
        before = asdict(show)
        changes = {"description": None, "performer": None, "runtime": None}
        changed = show.with_changes(changes, POLICY)
        self.assertEqual(asdict(changed), {**before, **changes})
        self.assertEqual(asdict(show), before)

    def test_invalid_changes_leave_the_original_unchanged(self):
        show = Show(**show_values())
        before = asdict(show)
        for changes in ({"title": ""}, {"type": None}, {"runtime": 0}):
            with self.subTest(changes=changes):
                with self.assertRaises(CatalogValidationError):
                    show.with_changes(changes, POLICY)
                self.assertEqual(asdict(show), before)

    def test_change_policy_checks_the_merged_object(self):
        show = Show(**show_values(type="CONCERT"))
        policy = CatalogPolicy(show_types=frozenset({"CLASS"}))
        with self.assertRaises(CatalogValidationError):
            show.with_changes({"title": "New title"}, policy)
        changed = show.with_changes({"type": "CLASS"}, policy)
        self.assertEqual(changed.type, "CLASS")
        self.assertEqual(show.type, "CONCERT")

    def test_changes_reject_identity_owner_audit_and_unknown_fields(self):
        show = Show(**show_values())
        before = asdict(show)
        for field, value in (
            ("show_id", 99), ("user_id", 99), ("created_at", T0),
            ("updated_at", T0), ("unknown_field", "value"),
        ):
            with self.subTest(field=field):
                with self.assertRaises(CatalogValidationError):
                    show.with_changes({field: value}, POLICY)
                self.assertEqual(asdict(show), before)

    def test_objects_remain_frozen_after_a_valid_change(self):
        show = Show(**show_values())
        changed = show.with_changes({"title": "Updated"}, POLICY)
        for entity in (show, changed):
            with self.subTest(entity=entity):
                with self.assertRaises(FrozenInstanceError):
                    entity.title = "Bypass"


class PerformanceDomainTests(unittest.TestCase):
    def test_constructor_rejects_invalid_round_and_ticket_limit(self):
        for field in ("round_number", "max_tickets_per_user"):
            for value in (0, -1, True, "1"):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(CatalogValidationError):
                        Performance(**performance_values(**{field: value}))

    def test_constructor_requires_aware_datetimes(self):
        for field in ("booking_opens_at", "booking_closes_at", "starts_at", "ends_at"):
            with self.subTest(field=field):
                with self.assertRaises(CatalogValidationError):
                    Performance(**performance_values(**{field: T0.replace(tzinfo=None)}))
        with self.assertRaises(CatalogValidationError):
            Performance(**performance_values(starts_at=None))

    def test_constructor_rejects_invalid_time_order(self):
        cases = (
            {"booking_opens_at": T0 - timedelta(hours=1)},
            {"booking_closes_at": T0 + timedelta(minutes=1)},
            {"ends_at": T0},
            {"ends_at": T0 - timedelta(minutes=1)},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                with self.assertRaises(CatalogValidationError):
                    Performance(**performance_values(**changes))

    def test_booking_may_close_exactly_at_performance_start(self):
        performance = Performance(**performance_values(booking_closes_at=T0))
        self.assertEqual(performance.booking_closes_at, performance.starts_at)

    def test_constructor_rejects_invalid_status_text(self):
        for value in ("", "   ", "x" * 31, None):
            with self.subTest(value=value):
                with self.assertRaises(CatalogValidationError):
                    Performance(**performance_values(status=value))

    def test_past_schedule_and_unconfigured_status_are_preserved(self):
        starts = datetime(2001, 1, 1, 19, tzinfo=KST)
        values = performance_values(
            starts_at=starts, ends_at=starts + timedelta(hours=2),
            booking_opens_at=starts - timedelta(days=7),
            booking_closes_at=starts - timedelta(hours=1), status="TEAM_CUSTOM_STATUS",
        )
        performance = Performance(**values)
        self.assertEqual(asdict(performance), values)
        self.assertIs(performance.starts_at.tzinfo, KST)
        self.assertEqual(performance.max_tickets_per_user, 3)

    def test_creation_validation_needs_no_ids_and_does_not_mutate_input(self):
        values = performance_creation_values()
        before = dict(values)
        self.assertIsNone(Performance.validate_creation(MappingProxyType(values), POLICY))
        self.assertEqual(values, before)
        self.assertNotIn("perf_id", values)
        self.assertNotIn("show_id", values)

    def test_creation_validation_rejects_bad_schedule_without_mutating_input(self):
        values = performance_creation_values(ends_at=T0 - timedelta(minutes=1))
        before = dict(values)
        with self.assertRaises(CatalogValidationError):
            Performance.validate_creation(values, POLICY)
        self.assertEqual(values, before)

    def test_creation_validation_applies_explicit_status_allowlist(self):
        policy = CatalogPolicy(performance_statuses=frozenset({"ON_SALE"}))
        with self.assertRaises(CatalogValidationError):
            Performance.validate_creation(performance_creation_values(), policy)
        self.assertIsNone(Performance.validate_creation(
            performance_creation_values(status="ON_SALE"), policy,
        ))

    def test_partial_change_returns_new_object_and_preserves_omitted_fields(self):
        performance = Performance(**performance_values())
        before = asdict(performance)
        changes = {"status": "ON_SALE"}
        changed = performance.with_changes(MappingProxyType(changes), POLICY)
        self.assertIsNot(changed, performance)
        self.assertEqual(asdict(changed), {**before, **changes})
        self.assertEqual(asdict(performance), before)
        self.assertEqual(changes, {"status": "ON_SALE"})

    def test_partial_schedule_change_is_checked_against_the_existing_values(self):
        performance = Performance(**performance_values())
        before = asdict(performance)
        with self.assertRaises(CatalogValidationError):
            performance.with_changes({"ends_at": T0 - timedelta(minutes=1)}, POLICY)
        self.assertEqual(asdict(performance), before)
        changes = {"starts_at": T0 + timedelta(hours=3), "ends_at": T0 + timedelta(hours=5)}
        self.assertEqual(asdict(performance.with_changes(changes, POLICY)), {**before, **changes})

    def test_null_changes_do_not_erase_required_values(self):
        performance = Performance(**performance_values())
        before = asdict(performance)
        for field in ("round_number", "starts_at", "ends_at", "booking_opens_at",
                      "booking_closes_at", "max_tickets_per_user", "status"):
            with self.subTest(field=field):
                with self.assertRaises(CatalogValidationError):
                    performance.with_changes({field: None}, POLICY)
                self.assertEqual(asdict(performance), before)

    def test_change_policy_checks_the_merged_object(self):
        performance = Performance(**performance_values(status="SCHEDULED"))
        policy = CatalogPolicy(performance_statuses=frozenset({"ON_SALE"}))
        with self.assertRaises(CatalogValidationError):
            performance.with_changes({"round_number": 2}, policy)
        self.assertEqual(performance.with_changes({"status": "ON_SALE"}, policy).status, "ON_SALE")
        self.assertEqual(performance.status, "SCHEDULED")

    def test_schedule_validation_precedes_status_policy_for_combined_errors(self):
        performance = Performance(**performance_values())
        policy = CatalogPolicy(performance_statuses=frozenset({"SCHEDULED"}))
        with self.assertRaisesRegex(CatalogValidationError, "예매 시작"):
            performance.with_changes({"ends_at": T0 - timedelta(minutes=1), "status": "OTHER"}, policy)

    def test_changes_reject_identity_parent_and_unknown_fields(self):
        performance = Performance(**performance_values())
        before = asdict(performance)
        for field, value in (("perf_id", 99), ("show_id", 99), ("unknown_field", "value")):
            with self.subTest(field=field):
                with self.assertRaises(CatalogValidationError):
                    performance.with_changes({field: value}, POLICY)
                self.assertEqual(asdict(performance), before)

    def test_objects_remain_frozen_after_a_valid_change(self):
        performance = Performance(**performance_values())
        changed = performance.with_changes({"status": "ON_SALE"}, POLICY)
        for entity in (performance, changed):
            with self.subTest(entity=entity):
                with self.assertRaises(FrozenInstanceError):
                    entity.status = "Bypass"


if __name__ == "__main__":
    unittest.main()