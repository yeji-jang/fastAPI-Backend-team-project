"""좌석 구성 쓰기 API의 성공·권한·판매 시각·중복 검사와 저장 결과를 SQLite에서 확인한다."""

from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import BigInteger, Column, MetaData, String, Table, insert, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from asyncticket.seats.application.service import SeatInfoService
from asyncticket.seats.infrastructure.repositories import (
    SqlAlchemyPerformanceSeatRepository,
    SqlAlchemySeatInfoRepository,
)
from asyncticket.seats.infrastructure.models import PerformanceSeats, SeatsInfoModel
from asyncticket.seats.presentation.router import router
from asyncticket.shared.core.exception_handlers import register_exception_handlers
from asyncticket.shared.domain.catalog import CatalogActor, CatalogPolicy
from asyncticket.shared.presentation.catalog_auth import get_current_catalog_actor
from asyncticket.shared.presentation.catalog_http import register_catalog_errors
from asyncticket.wiring.seats import provide_seat_info_service, wire_dependencies


class SeatConfigurationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.addAsyncCleanup(self.engine.dispose)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        metadata = MetaData()
        shows = Table(
            "shows",
            metadata,
            Column("show_id", BigInteger, primary_key=True),
            Column("user_id", BigInteger, nullable=False),
        )
        performances = Table(
            "performances",
            metadata,
            Column("perf_id", BigInteger, primary_key=True),
            Column("show_id", BigInteger, nullable=False),
            # SQLite가 시간대 정보를 버리지 않도록 ISO 문자열로 넣는다.
            Column("booking_opens_at", String, nullable=False),
        )
        Table(
            "reservations", metadata, Column("reserv_id", BigInteger, primary_key=True)
        )
        # ORM flush도 FK 대상을 찾을 수 있도록 테스트용 부모 메타데이터만 보충한다.
        self.parent_stubs = []
        self.addCleanup(self._remove_parent_stubs)
        for name in ("performances", "reservations"):
            if name not in SeatsInfoModel.metadata.tables:
                self.parent_stubs.append(
                    metadata.tables[name].to_metadata(SeatsInfoModel.metadata)
                )
        SeatsInfoModel.__table__.to_metadata(metadata)
        PerformanceSeats.__table__.to_metadata(metadata)
        async with self.engine.begin() as conn:
            await conn.execute(text("PRAGMA foreign_keys = ON"))
            await conn.run_sync(metadata.create_all)
            await conn.execute(insert(shows), {"show_id": 1, "user_id": 7})
            await conn.execute(
                insert(performances),
                {
                    "perf_id": 10,
                    "show_id": 1,
                    "booking_opens_at": (
                        datetime.now(timezone.utc) + timedelta(days=1)
                    ).isoformat(),
                },
            )

        async def test_db():
            async with self.sessions() as session:
                yield session

        self.app = FastAPI()
        register_exception_handlers(self.app)
        register_catalog_errors(self.app)
        self.app.include_router(router)
        wire_dependencies(self.app, db_dependency=test_db)
        self.app.dependency_overrides[get_current_catalog_actor] = lambda: CatalogActor(
            user_id=7,
            role="SELLER",
        )
        self.client = AsyncClient(
            transport=ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://test",
        )

        self.addAsyncCleanup(self.client.aclose)

    def _remove_parent_stubs(self):
        for stub in self.parent_stubs:
            SeatsInfoModel.metadata.remove(stub)

    async def test_create_configuration_commits_grade_and_available_seats(self):
        await self._assert_create_configuration(30000)

    async def test_create_configuration_accepts_zero_price(self):
        await self._assert_create_configuration(0)

    async def _assert_create_configuration(self, price):
        response = await self.client.post(
            "/v1/performances/10/seat-infos",
            json={
                "name": "R석",
                "total_seat": 2,
                "price": price,
                "seat_seqs": ["A01", "A02"],
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["code"], "OK")
        grade_id = body["data"]["seat_id"]
        self.assertEqual(
            body["data"],
            {
                "seat_id": grade_id,
                "perf_id": 10,
                "name": "R석",
                "total_seat": 2,
                "price": price,
            },
        )
        self.assertEqual(
            response.headers["Location"], f"/v1/performances/10/seat-infos/{grade_id}"
        )
        # 요청 세션이 닫힌 후 별도 세션에서 등급과 개별 좌석 저장을 확인한다.
        async with self.sessions() as session:
            grades = (await session.scalars(select(SeatsInfoModel))).all()
            self.assertEqual(len(grades), 1)
            grade = grades[0]
            self.assertEqual(grade.seat_id, grade_id)
            self.assertEqual(
                (grade.perf_id, grade.name, grade.total_seat, grade.price),
                (10, "R석", 2, price),
            )
            seats = (
                await session.scalars(
                    select(PerformanceSeats).order_by(
                        PerformanceSeats.seat_seq,
                    )
                )
            ).all()
            self.assertEqual(
                [(s.seat_id2, s.seat_seq, s.status, s.reserv_id) for s in seats],
                [
                    (grade_id, "A01", "AVAILABLE", None),
                    (grade_id, "A02", "AVAILABLE", None),
                ],
            )

    async def test_update_price_commits_without_changing_configuration(self):
        async with self.sessions() as session:
            await session.execute(
                insert(SeatsInfoModel).values(
                    seat_id=101,
                    perf_id=10,
                    name="S석",
                    total_seat=1,
                    price=30000,
                )
            )
            await session.execute(
                insert(PerformanceSeats).values(
                    perf_seat_id=1001,
                    seat_id2=101,
                    seat_seq="B01",
                    status="AVAILABLE",
                    reserv_id=None,
                )
            )
            await session.commit()

        for price in (49999, 0):
            with self.subTest(price=price):
                response = await self.client.patch(
                    "/v1/performances/10/seat-infos/101",
                    json={"price": price},
                )
                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                self.assertTrue(body["success"])
                self.assertEqual(body["code"], "OK")
                self.assertEqual(
                    body["data"],
                    {
                        "seat_id": 101,
                        "perf_id": 10,
                        "name": "S석",
                        "total_seat": 1,
                        "price": price,
                    },
                )
                async with self.sessions() as session:
                    grade = await session.get(SeatsInfoModel, 101)
                    self.assertEqual(
                        (grade.perf_id, grade.name, grade.total_seat, grade.price),
                        (10, "S석", 1, price),
                    )
                    seats = (await session.scalars(select(PerformanceSeats))).all()
                    self.assertEqual(
                        [
                            (
                                s.perf_seat_id,
                                s.seat_id2,
                                s.seat_seq,
                                s.status,
                                s.reserv_id,
                            )
                            for s in seats
                        ],
                        [(1001, 101, "B01", "AVAILABLE", None)],
                    )

    async def test_non_owner_cannot_create_configuration(self):
        self.app.dependency_overrides[get_current_catalog_actor] = lambda: CatalogActor(
            user_id=8,
            role="SELLER",
        )
        response = await self.client.post(
            "/v1/performances/10/seat-infos",
            json={
                "name": "R석",
                "total_seat": 2,
                "price": 30000,
                "seat_seqs": ["A01", "A02"],
            },
        )
        self.assertEqual(response.status_code, 403, response.text)
        body = response.json()
        self.assertFalse(body["success"])
        self.assertEqual(body["code"], "PERMISSION_DENIED")
        self.assertIsNone(body["data"])
        async with self.sessions() as session:
            self.assertEqual((await session.scalars(select(SeatsInfoModel))).all(), [])
            self.assertEqual(
                (await session.scalars(select(PerformanceSeats))).all(), []
            )

    async def test_non_owner_cannot_update_price(self):
        async with self.sessions() as session:
            await session.execute(
                insert(SeatsInfoModel).values(
                    seat_id=101,
                    perf_id=10,
                    name="S석",
                    total_seat=1,
                    price=30000,
                )
            )
            await session.execute(
                insert(PerformanceSeats).values(
                    perf_seat_id=1001,
                    seat_id2=101,
                    seat_seq="B01",
                    status="AVAILABLE",
                    reserv_id=None,
                )
            )
            await session.commit()
        self.app.dependency_overrides[get_current_catalog_actor] = lambda: CatalogActor(
            user_id=8,
            role="SELLER",
        )
        response = await self.client.patch(
            "/v1/performances/10/seat-infos/101",
            json={"price": 0},
        )
        self.assertEqual(response.status_code, 403, response.text)
        body = response.json()
        self.assertFalse(body["success"])
        self.assertEqual(body["code"], "PERMISSION_DENIED")
        self.assertIsNone(body["data"])
        async with self.sessions() as session:
            grades = (await session.scalars(select(SeatsInfoModel))).all()
            self.assertEqual(
                [(g.seat_id, g.perf_id, g.name, g.total_seat, g.price) for g in grades],
                [(101, 10, "S석", 1, 30000)],
            )
            seats = (await session.scalars(select(PerformanceSeats))).all()
            self.assertEqual(
                [
                    (s.perf_seat_id, s.seat_id2, s.seat_seq, s.status, s.reserv_id)
                    for s in seats
                ],
                [(1001, 101, "B01", "AVAILABLE", None)],
            )

    async def _seed_configuration(self):
        async with self.sessions() as session:
            await session.execute(
                insert(SeatsInfoModel).values(
                    seat_id=101,
                    perf_id=10,
                    name="S석",
                    total_seat=1,
                    price=30000,
                )
            )
            await session.execute(
                insert(PerformanceSeats).values(
                    perf_seat_id=1001,
                    seat_id2=101,
                    seat_seq="B01",
                    status="AVAILABLE",
                    reserv_id=None,
                )
            )
            await session.commit()

    async def _configuration_snapshot(self):
        async with self.sessions() as session:
            grades = (
                await session.scalars(
                    select(SeatsInfoModel).order_by(
                        SeatsInfoModel.seat_id,
                    )
                )
            ).all()
            seats = (
                await session.scalars(
                    select(PerformanceSeats).order_by(
                        PerformanceSeats.perf_seat_id,
                    )
                )
            ).all()
            return (
                [(g.seat_id, g.perf_id, g.name, g.total_seat, g.price) for g in grades],
                [
                    (s.perf_seat_id, s.seat_id2, s.seat_seq, s.status, s.reserv_id)
                    for s in seats
                ],
            )

    async def _set_sale_started(self):
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE performances SET booking_opens_at = :opened_at WHERE perf_id = 10"
                ),
                {
                    "opened_at": (
                        datetime.now(timezone.utc) - timedelta(days=1)
                    ).isoformat()
                },
            )

    def _assert_conflict(self, response, code, message):
        self.assertEqual(response.status_code, 409, response.text)
        body = response.json()
        self.assertFalse(body["success"])
        self.assertEqual(body["code"], code)
        self.assertEqual(body["message"], message)
        self.assertIsNone(body["data"])

    async def test_sale_started_blocks_configuration_creation(self):
        await self._seed_configuration()
        await self._set_sale_started()
        before = await self._configuration_snapshot()
        response = await self.client.post(
            "/v1/performances/10/seat-infos",
            json={
                "name": "R석",
                "total_seat": 1,
                "price": 30000,
                "seat_seqs": ["A01"],
            },
        )
        self._assert_conflict(
            response,
            "SEAT_SALE_STARTED",
            "판매 시작 후 좌석 구성을 변경할 수 없습니다.",
        )
        self.assertEqual(await self._configuration_snapshot(), before)

    async def test_sale_started_blocks_price_update(self):
        await self._seed_configuration()
        await self._set_sale_started()
        before = await self._configuration_snapshot()
        response = await self.client.patch(
            "/v1/performances/10/seat-infos/101",
            json={"price": 0},
        )
        self._assert_conflict(
            response,
            "SEAT_SALE_STARTED",
            "판매 시작 후 좌석 구성을 변경할 수 없습니다.",
        )
        self.assertEqual(await self._configuration_snapshot(), before)

    async def test_duplicate_grade_in_same_performance_is_rejected(self):
        await self._seed_configuration()
        before = await self._configuration_snapshot()
        # 좌석명은 새 값으로 보내 등급 중복 검사만 확인한다.
        response = await self.client.post(
            "/v1/performances/10/seat-infos",
            json={
                "name": "S석",
                "total_seat": 1,
                "price": 0,
                "seat_seqs": ["B02"],
            },
        )
        self._assert_conflict(
            response, "CONFLICT", "같은 회차에 이미 등록된 좌석 등급입니다."
        )
        self.assertEqual(await self._configuration_snapshot(), before)

    async def test_existing_seat_name_in_same_performance_is_rejected(self):
        await self._seed_configuration()
        before = await self._configuration_snapshot()
        # 등급은 새 값으로 보내 기존 좌석명과의 충돌을 확인한다.
        response = await self.client.post(
            "/v1/performances/10/seat-infos",
            json={
                "name": "R석",
                "total_seat": 2,
                "price": 30000,
                "seat_seqs": ["A01", "B01"],
            },
        )
        self._assert_conflict(
            response, "CONFLICT", "같은 회차에 이미 등록된 좌석명입니다."
        )
        self.assertEqual(await self._configuration_snapshot(), before)

    async def test_duplicate_seat_names_in_request_are_rejected(self):
        await self._seed_configuration()
        before = await self._configuration_snapshot()
        response = await self.client.post(
            "/v1/performances/10/seat-infos",
            json={
                "name": "R석",
                "total_seat": 2,
                "price": 30000,
                "seat_seqs": ["A01", "A01"],
            },
        )
        self.assertEqual(response.status_code, 422, response.text)
        body = response.json()
        self.assertFalse(body["success"])
        self.assertEqual(body["code"], "REQUEST_VALIDATION_ERROR")
        self.assertIsNone(body["data"])
        self.assertEqual(await self._configuration_snapshot(), before)

    async def test_partial_seat_write_failure_rolls_back_grade_and_seats(self):
        await self._assert_failed_creation_rolls_back("seat_write")

    async def test_commit_failure_rolls_back_grade_and_seats(self):
        await self._assert_failed_creation_rolls_back("commit")

    async def _assert_failed_creation_rolls_back(self, failure_point):
        await self._seed_configuration()
        before = await self._configuration_snapshot()
        payload = {
            "name": "R석",
            "total_seat": 2,
            "price": 30000,
            "seat_seqs": ["A01", "A02"],
        }
        # 요청 후에도 세션을 열어 두어 close의 자동 rollback으로 통과하지 않게 한다.
        async with self.sessions() as session:
            grade_repository = SqlAlchemySeatInfoRepository(session)
            seat_repository = SqlAlchemyPerformanceSeatRepository(session)
            service = SeatInfoService(
                grade_repository, seat_repository, CatalogPolicy()
            )
            self.app.dependency_overrides[provide_seat_info_service] = lambda: service
            real_save_many = seat_repository.save_many
            reached_failure_point = []

            async def fail_after_partial_write(seats):
                await real_save_many(seats[:1])
                grades = (await session.scalars(select(SeatsInfoModel))).all()
                written = (await session.scalars(select(PerformanceSeats))).all()
                self.assertEqual(len(grades), 2)
                self.assertEqual(len(written), 2)
                reached_failure_point.append("seat_write")
                raise RuntimeError("injected seat write failure")

            async def fail_before_commit():
                grades = (await session.scalars(select(SeatsInfoModel))).all()
                written = (await session.scalars(select(PerformanceSeats))).all()
                self.assertEqual(len(grades), 2)
                self.assertEqual(len(written), 3)
                reached_failure_point.append("commit")
                raise RuntimeError("injected commit failure")

            repository, method, failure = (
                (seat_repository, "save_many", fail_after_partial_write)
                if failure_point == "seat_write"
                else (grade_repository, "commit", fail_before_commit)
            )
            with patch.object(
                repository, method, new=AsyncMock(side_effect=failure)
            ) as failed, patch.object(
                grade_repository,
                "rollback",
                new=AsyncMock(
                    wraps=grade_repository.rollback,
                ),
            ) as rolled_back:
                response = await self.client.post(
                    "/v1/performances/10/seat-infos",
                    json=payload,
                )
                self.assertEqual(response.status_code, 500, response.text)
                self.assertEqual(response.json()["code"], "INTERNAL_SERVER_ERROR")
                self.assertFalse(response.json()["success"])
                self.assertIsNone(response.json()["data"])
                self.assertEqual(reached_failure_point, [failure_point])
                failed.assert_awaited_once()
                rolled_back.assert_awaited_once()
                # 세션이 닫히기 전에 서비스가 직접 rollback했는지 확인한다.
                self.assertFalse(session.in_transaction())
                self.assertEqual(await self._configuration_snapshot(), before)

            # 실패 후 같은 세션으로 정상 요청을 재시도할 수 있어야 한다.
            retry = await self.client.post(
                "/v1/performances/10/seat-infos", json=payload
            )
            self.assertEqual(retry.status_code, 201, retry.text)
        after_grades, after_seats = await self._configuration_snapshot()
        self.assertEqual(len(after_grades), 2)
        self.assertEqual(len(after_seats), 3)

    async def test_corrupt_stored_price_returns_server_error(self):
        await self._seed_configuration()
        async with self.sessions() as session:
            await session.execute(
                text("UPDATE seats_info SET price=-1 WHERE seat_id=101")
            )
            await session.commit()
        response = await self.client.patch(
            "/v1/performances/10/seat-infos/101",
            json={"price": 100},
        )
        self.assertEqual(response.status_code, 500, response.text)
        self.assertEqual(response.json()["code"], "INTERNAL_SERVER_ERROR")
        async with self.sessions() as session:
            self.assertEqual(
                await session.scalar(
                    text("SELECT price FROM seats_info WHERE seat_id=101")
                ),
                -1,
            )
