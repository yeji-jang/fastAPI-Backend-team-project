"""실제 좌석 SELECT와 SQLite 상태 변경을 연결해 캐시 히트를 검사한다."""

import unittest
from unittest.mock import AsyncMock, Mock

from sqlalchemy import BigInteger, Column, MetaData, Table, insert, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from asyncticket.seats.application.service import PerformanceSeatService
from asyncticket.seats.infrastructure.cache import RedisSeatListCache
from asyncticket.seats.infrastructure.models import PerformanceSeats, SeatsInfoModel
from asyncticket.seats.infrastructure.repositories import (
    SqlAlchemyPerformanceSeatRepository,
    SqlAlchemySeatInfoRepository,
)


class SeatCacheSqliteTests(unittest.IsolatedAsyncioTestCase):
    async def test_current_status_and_changed_seat_list_are_read_from_database(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.addAsyncCleanup(engine.dispose)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        metadata = MetaData()
        performances = Table(
            "performances", metadata, Column("perf_id", BigInteger, primary_key=True)
        )
        Table(
            "reservations", metadata, Column("reserv_id", BigInteger, primary_key=True)
        )
        grades = SeatsInfoModel.__table__.to_metadata(metadata)
        seats = PerformanceSeats.__table__.to_metadata(metadata)
        async with engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
            await conn.execute(insert(performances), [{"perf_id": 10}, {"perf_id": 20}])
            await conn.execute(
                insert(grades),
                [
                    dict(seat_id=1, perf_id=10, name="R석", total_seat=2, price=30000),
                    dict(seat_id=2, perf_id=20, name="S석", total_seat=1, price=10000),
                ],
            )
            await conn.execute(
                insert(seats),
                [
                    dict(
                        perf_seat_id=101, seat_id2=1, seat_seq="A01", status="AVAILABLE"
                    ),
                    dict(
                        perf_seat_id=201, seat_id2=2, seat_seq="B01", status="OCCUPIED"
                    ),
                ],
            )
        stored = {}
        client = Mock()
        client.get = AsyncMock(side_effect=lambda key: stored.get(key))
        client.set = AsyncMock(
            side_effect=lambda key, value, **kwargs: stored.__setitem__(key, value)
        )
        cache = RedisSeatListCache(client)
        async with sessions() as session:
            repo = SqlAlchemyPerformanceSeatRepository(session)
            repo.list_performance_seats = AsyncMock(wraps=repo.list_performance_seats)
            service = PerformanceSeatService(
                repo, SqlAlchemySeatInfoRepository(session), cache
            )
            first = await service.list_performance_seats(10)
            self.assertEqual([item["perf_seat_id"] for item in first], [101])
            await session.execute(
                update(seats)
                .where(seats.c.perf_seat_id == 101)
                .values(status="RESERVED")
            )
            await session.commit()
            second = await service.list_performance_seats(10)
            self.assertEqual(second[0]["status"], "RESERVED")
            self.assertEqual(repo.list_performance_seats.await_count, 1)
            await session.execute(
                insert(seats),
                dict(perf_seat_id=102, seat_id2=1, seat_seq="A02", status="AVAILABLE"),
            )
            await session.commit()
            third = await service.list_performance_seats(10)
            self.assertEqual([item["perf_seat_id"] for item in third], [101, 102])
            self.assertEqual(repo.list_performance_seats.await_count, 2)
            # 새로 채운 캐시가 다시 히트해도 해제된 상태는 DB에서 읽는다.
            await session.execute(
                update(seats)
                .where(seats.c.perf_seat_id == 101)
                .values(status="AVAILABLE")
            )
            await session.commit()
            fourth = await service.list_performance_seats(10)
            self.assertEqual(fourth[0]["status"], "AVAILABLE")
            self.assertEqual(repo.list_performance_seats.await_count, 2)
            # 실제 라우터와 wiring도 같은 캐시를 주입하고 기존 응답 형식을 유지한다.
            from fastapi import FastAPI
            from httpx import ASGITransport, AsyncClient
            from asyncticket.seats.presentation.router import router
            from asyncticket.wiring.performance_seats import (
                provide_seat_list_cache,
                wire_dependencies,
            )

            async def test_db():
                yield session

            app = FastAPI()
            app.include_router(router)
            wire_dependencies(app, db_dependency=test_db)
            app.dependency_overrides[provide_seat_list_cache] = lambda: cache
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as http:
                response = await http.get("/v1/performances/10/seats")
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["data"]["items"], fourth)
