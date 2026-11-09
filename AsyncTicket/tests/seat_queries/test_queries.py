"""실행: DATABASE_URL=postgresql+asyncpg://test:test@127.0.0.1:5432/test uv run --with httpx --with aiosqlite python -B -m unittest discover -s tests/seat_queries -v

실제 팀 PostgreSQL 대신 메모리 안의 SQLite에서 조회·응답 동작만 검사한다.
공연·예매의 최소 부모 테이블은 이 테스트의 FK 검사에만 사용하는 픽스처다.
"""

import ast
from pathlib import Path
import unittest

from httpx import ASGITransport, AsyncClient
from sqlalchemy import BigInteger, Column, MetaData, Table, insert, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from asyncticket.wiring.performance_seats import wire_dependencies
from asyncticket.seats.infrastructure.models import PerformanceSeats
from asyncticket.seats.infrastructure.models import SeatsInfoModel
from asyncticket.seats.infrastructure.repositories import (
    SqlAlchemyPerformanceSeatRepository,
)
from asyncticket.seats.infrastructure.repositories import SqlAlchemySeatInfoRepository
from fastapi import FastAPI
from asyncticket.seats.presentation.router import router as seat_router
from asyncticket.shared.core.exception_handlers import register_exception_handlers


class SeatQueryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

        metadata = MetaData()
        performances = Table(
            "performances",
            metadata,
            Column("perf_id", BigInteger, primary_key=True),
        )
        reservations = Table(
            "reservations",
            metadata,
            Column("reserv_id", BigInteger, primary_key=True),
            Column("perf_id", BigInteger, nullable=False),
        )
        seat_infos = SeatsInfoModel.__table__.to_metadata(metadata)
        seats = PerformanceSeats.__table__.to_metadata(metadata)

        async with self.engine.begin() as conn:
            await conn.execute(text("PRAGMA foreign_keys = ON"))
            await conn.run_sync(metadata.create_all)
            await conn.execute(
                insert(performances),
                [
                    {"perf_id": 10},
                    {"perf_id": 20},
                    {"perf_id": 30},
                ],
            )
            await conn.execute(
                insert(reservations),
                [{"reserv_id": 1, "perf_id": 10}, {"reserv_id": 2, "perf_id": 20}],
            )
            await conn.execute(
                insert(seat_infos),
                [
                    {
                        "seat_id": 101,
                        "perf_id": 10,
                        "name": "R석",
                        "total_seat": 30,
                        "price": 55000,
                    },
                    {
                        "seat_id": 102,
                        "perf_id": 20,
                        "name": "S석",
                        "total_seat": 20,
                        "price": 30000,
                    },
                    {
                        "seat_id": 103,
                        "perf_id": 10,
                        "name": None,
                        "total_seat": None,
                        "price": None,
                    },
                ],
            )
            await conn.execute(
                insert(seats),
                [
                    {
                        "perf_seat_id": 1001,
                        "reserv_id": 1,
                        "seat_id2": 101,
                        "status": "RESERVED",
                        "seat_seq": "A01",
                    },
                    {
                        "perf_seat_id": 1002,
                        "reserv_id": 1,
                        "seat_id2": 102,
                        "status": "RESERVED",
                        "seat_seq": "A01",
                    },
                    {
                        "perf_seat_id": 1003,
                        "reserv_id": 1,
                        "seat_id2": 103,
                        "status": "RESERVED",
                        "seat_seq": None,
                    },
                ],
            )

        async def get_test_db():
            async with self.sessions() as session:
                yield session

        # 다른 담당자의 ORM 초기화와 분리한 좌석 전용 HTTP 검사 앱이다.
        self.app = FastAPI()
        register_exception_handlers(self.app)
        self.app.include_router(seat_router)
        wire_dependencies(self.app, db_dependency=get_test_db)
        self.client = AsyncClient(
            transport=ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://test",
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.engine.dispose()

    async def test_unbooked_seat_can_be_linked_without_committing(self):
        from asyncticket.seats.application.service import (
            PerformanceSeatService,
            SeatReservationConflictError,
        )

        async with self.sessions() as session:
            await session.execute(
                insert(PerformanceSeats).values(
                    perf_seat_id=2001,
                    reserv_id=None,
                    seat_id2=101,
                    status="TEST_AVAILABLE",
                    seat_seq="B01",
                )
            )
            await session.commit()
            service = PerformanceSeatService(
                SqlAlchemyPerformanceSeatRepository(session),
                SqlAlchemySeatInfoRepository(session),
            )
            args = dict(
                perf_id=10,
                perf_seat_id=2001,
                reserv_id=1,
                expected_status="TEST_AVAILABLE",
                reserved_status="TEST_RESERVED",
            )
            # 다른 회차의 예매나 잘못된 상태로는 연결할 수 없다.
            for override in (
                {"reserv_id": 2},
                {"reserv_id": 999},
                {"perf_id": 20},
                {"expected_status": "WRONG"},
            ):
                with self.assertRaises(SeatReservationConflictError):
                    await service.assign_reservation(**(args | override))
            await service.assign_reservation(**args)
            seat = await session.get(PerformanceSeats, 2001)
            self.assertEqual((seat.reserv_id, seat.status), (1, "TEST_RESERVED"))
            with self.assertRaises(SeatReservationConflictError):
                await service.assign_reservation(**args)
            # 좌석 함수 안에서 commit하지 않아 예매 실패 시 함께 복구할 수 있다.
            await session.rollback()
        async with self.sessions() as session:
            seat = await session.get(PerformanceSeats, 2001)
            self.assertEqual((seat.reserv_id, seat.status), (None, "TEST_AVAILABLE"))
            await PerformanceSeatService(
                SqlAlchemyPerformanceSeatRepository(session),
                SqlAlchemySeatInfoRepository(session),
            ).assign_reservation(**args)
            await session.commit()
        async with self.sessions() as session:
            seat = await session.get(PerformanceSeats, 2001)
            self.assertEqual((seat.reserv_id, seat.status), (1, "TEST_RESERVED"))

    async def test_invalid_reservation_link_uses_common_validation_exception(self):
        from asyncticket.seats.application.service import PerformanceSeatService
        from asyncticket.shared.core.exceptions import ValidationException

        async with self.sessions() as session:
            service = PerformanceSeatService(
                SqlAlchemyPerformanceSeatRepository(session),
                SqlAlchemySeatInfoRepository(session),
            )
            args = dict(
                perf_id=10,
                perf_seat_id=1001,
                reserv_id=1,
                expected_status="TEST_AVAILABLE",
                reserved_status="TEST_RESERVED",
            )
            for override, code in (
                ({"reserv_id": 0}, "INVALID_SEAT_RESERVATION_ID"),
                (
                    {"reserved_status": "TEST_AVAILABLE"},
                    "INVALID_SEAT_STATUS_TRANSITION",
                ),
            ):
                with self.subTest(override=override):
                    with self.assertRaises(ValidationException) as raised:
                        await service.assign_reservation(**(args | override))
                    self.assertEqual(raised.exception.status_code, 422)
                    self.assertEqual(raised.exception.error_code, code)

    async def test_list_filters_by_performance_and_excludes_reservation_id(self):
        response = await self.client.get("/v1/performances/10/seats")
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["perf_id"], 10)
        self.assertEqual([item["perf_seat_id"] for item in data["items"]], [1001, 1003])
        for item in data["items"]:
            self.assertNotIn("reserv_id", item)
        self.assertEqual(data["items"][0]["seat_id"], 101)
        self.assertEqual(data["items"][0]["grade"], "R석")

    async def test_existing_performance_without_seats_returns_empty_list(self):
        response = await self.client.get("/v1/performances/30/seats")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"], {"perf_id": 30, "items": []})

    async def test_missing_performance_returns_404(self):
        response = await self.client.get("/v1/performances/999/seats")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["message"], "공연 회차를 찾을 수 없습니다.")

    async def test_detail_uses_both_performance_and_seat_sequence(self):
        first = await self.client.get("/v1/performances/10/seats/A01")
        second = await self.client.get("/v1/performances/20/seats/A01")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["data"]["perf_seat_id"], 1001)
        self.assertEqual(second.json()["data"]["perf_seat_id"], 1002)
        self.assertEqual(second.json()["data"]["status"], "RESERVED")

    async def test_detail_supports_slash_in_seat_sequence(self):
        async with self.sessions() as session:
            await session.execute(
                insert(PerformanceSeats).values(
                    perf_seat_id=9001,
                    seat_id2=101,
                    seat_seq="A/01",
                    status="AVAILABLE",
                    reserv_id=None,
                )
            )
            await session.commit()

        for seat_path in ("A/01", "A%2F01"):
            with self.subTest(seat_path=seat_path):
                response = await self.client.get(
                    f"/v1/performances/10/seats/{seat_path}"
                )
                self.assertEqual(response.status_code, 200)
                data = response.json()["data"]
                self.assertEqual(data["perf_seat_id"], 9001)
                self.assertEqual(data["seat_seq"], "A/01")

    async def test_missing_seat_in_existing_performance_returns_404(self):
        for path in ("/v1/performances/10/seats/Z99", "/v1/performances/30/seats/A01"):
            with self.subTest(path=path):
                response = await self.client.get(path)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(
                    response.json()["message"], "해당 회차의 좌석을 찾을 수 없습니다."
                )

    async def test_invalid_performance_id_returns_422(self):
        for value in ("0", "-1", "wrong"):
            with self.subTest(value=value):
                response = await self.client.get(f"/v1/performances/{value}/seats")
                self.assertEqual(response.status_code, 422)

    async def test_nullable_grade_price_and_sequence_are_preserved(self):
        response = await self.client.get("/v1/performances/10/seats")
        item = response.json()["data"]["items"][1]
        self.assertIsNone(item["grade"])
        self.assertIsNone(item["price"])
        self.assertIsNone(item["seat_seq"])
        self.assertEqual(item["status"], "RESERVED")

    async def test_duplicate_seat_sequence_is_not_arbitrarily_selected(self):
        async with self.sessions() as session:
            await session.execute(
                insert(PerformanceSeats).values(
                    perf_seat_id=1004,
                    reserv_id=1,
                    seat_id2=101,
                    status="RESERVED",
                    seat_seq="A01",
                )
            )
            await session.commit()
        response = await self.client.get("/v1/performances/10/seats/A01")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["message"], "좌석 정보를 확인할 수 없습니다.")

    async def test_get_requests_do_not_modify_seat_state(self):
        await self.client.get("/v1/performances/10/seats")
        await self.client.get("/v1/performances/10/seats/A01")
        async with self.sessions() as session:
            seat = await session.get(PerformanceSeats, 1001)
            self.assertEqual(seat.status, "RESERVED")
            self.assertEqual(seat.reserv_id, 1)

    async def test_grade_repository_returns_domain_objects(self):
        async with self.sessions() as session:
            repository = SqlAlchemySeatInfoRepository(session)
            grade = await repository.get_seat_info(101)
            self.assertEqual(grade.name, "R석")
            self.assertIsNone(await repository.get_seat_info(999))
            # 미설정 DB 행은 조회용 값으로 보존하되 도메인 객체로 만들지 않는다.
            self.assertIsNone(await repository.get_seat_info_view(20, 101))
            view = await repository.get_seat_info_view(10, 103)
            self.assertIsNone(view["name"])
            with self.assertRaises(ValueError):
                await repository.get_seat_info(103)

    async def test_openapi_declares_common_success_and_failure_shapes(self):
        spec = self.app.openapi()
        responses = spec["paths"]["/v1/performances/{perf_id}/seats"]["get"][
            "responses"
        ]
        for code in ("200", "404", "422", "500"):
            self.assertIn(
                "APIResponse",
                responses[code]["content"]["application/json"]["schema"]["$ref"],
            )

    async def test_success_and_failures_have_common_envelope(self):
        for path, status, code in (
            ("/v1/performances/10/seats", 200, "OK"),
            ("/v1/performances/999/seats", 404, "PERFORMANCE_NOT_FOUND"),
            ("/v1/performances/10/seats/Z99", 404, "SEAT_NOT_FOUND"),
            ("/v1/performances/wrong/seats", 422, "REQUEST_VALIDATION_ERROR"),
        ):
            with self.subTest(path=path):
                response = await self.client.get(path)
                self.assertEqual(response.status_code, status)
                body = response.json()
                self.assertEqual(
                    set(body),
                    {"success", "code", "message", "errors", "data", "responded_at"},
                )
                self.assertEqual(body["success"], status == 200)
                self.assertEqual(body["code"], code)
                if status != 200:
                    self.assertIsNone(body["data"])
                if status == 422:
                    self.assertIn("path.perf_id", body["errors"])

    async def test_grade_wiring_uses_its_own_repository(self):
        from fastapi import Depends
        from asyncticket.seats.application.service import SeatInfoService
        from asyncticket.wiring.seats import provide_seat_info_service
        from asyncticket.wiring.seats import wire_dependencies as wire_grades

        async def get_test_db():
            async with self.sessions() as session:
                yield session

        wire_grades(self.app, db_dependency=get_test_db)

        @self.app.get("/test/grades")
        async def grades(service: SeatInfoService = Depends(provide_seat_info_service)):
            return await service.get_seat_info(101)

        response = await self.client.get("/test/grades")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["seat_id"], 101)

    async def test_upper_layers_do_not_import_infrastructure(self):
        root = Path(__file__).resolve().parents[2] / "src/asyncticket"
        for domain in ("seats",):
            seats = root / domain
            for folder in ("domain", "application", "presentation"):
                sources = list((seats / folder).glob("*.py"))
                self.assertTrue(sources, f"검사할 파일이 없습니다: {folder}")
                for source in sources:
                    tree = ast.parse(source.read_text(encoding="utf-8"))
                    imports = []
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ImportFrom):
                            imports.append(node.module or "")
                        elif isinstance(node, ast.Import):
                            imports.extend(alias.name for alias in node.names)
                    with self.subTest(file=source.name):
                        self.assertFalse(
                            any(
                                ".infrastructure" in name
                                or name.startswith("sqlalchemy")
                                or name == "asyncticket.shared.core.database"
                                for name in imports
                            )
                        )


if __name__ == "__main__":
    unittest.main()
