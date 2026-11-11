"""Changing reservation status must preserve its original confirmation time."""
import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine, select, update

from asyncticket.reservations.infrastructure.models import ReservationModel
from asyncticket.shared.core.models import init_models


class ReservationTimestampTests(unittest.TestCase):
    def test_cancel_and_other_updates_preserve_confirmation_timestamp(self):
        init_models()
        engine = create_engine("sqlite://")
        table = ReservationModel.__table__
        table.create(engine)
        confirmed = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        canceled = datetime(2026, 1, 3, tzinfo=timezone.utc)
        try:
            with engine.begin() as conn:
                conn.execute(table.insert().values(
                    reserv_id=1, order_number="timestamp-regression", user_id=1,
                    perf_id=1, quantity=1, total_amount=50000,
                    status="CONFIRMED", confirmed_at=confirmed,
                ))
                before = conn.scalar(select(table.c.confirmed_at))
                conn.execute(update(table).where(table.c.reserv_id == 1).values(
                    status="CANCELED", canceled_at=canceled,
                ))
                row = conn.execute(select(table)).mappings().one()
                self.assertEqual(row["confirmed_at"], before)
                self.assertEqual(row["status"], "CANCELED")
                conn.execute(update(table).values(order_number="changed-reference"))
                self.assertEqual(conn.scalar(select(table.c.confirmed_at)), before)
        finally:
            engine.dispose()
