"""상태는 DB에서 읽고, 캐시 장애는 조회·커밋 결과를 바꾸지 않는지 검사한다."""

import json
import os
import unittest
from unittest.mock import AsyncMock, Mock, patch

from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from asyncticket.seats.application.service import (
    PerformanceSeatService,
    SeatInfoService,
)
from asyncticket.seats.application.exceptions import PerformanceNotFoundError
from asyncticket.seats.domain.enums import SeatGrade
from asyncticket.seats.domain.seat_info import SeatInfo
from asyncticket.seats.infrastructure.cache import METADATA_FIELDS, RedisSeatListCache
from asyncticket.shared.domain.catalog import CatalogActor, CatalogPolicy
from asyncticket.wiring.performance_seats import provide_seat_list_cache


def row(status="AVAILABLE", *, perf_id=10, perf_seat_id=101):
    return dict(
        perf_seat_id=perf_seat_id,
        seat_id=1,
        perf_id=perf_id,
        grade="R석",
        seat_seq="A01",
        price=30000,
        status=status,
    )


class SeatCacheTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = Mock()
        self.client.get = AsyncMock(return_value=None)
        self.client.set = AsyncMock()
        self.client.delete = AsyncMock()
        self.cache = RedisSeatListCache(self.client)
        self.repo = Mock()
        self.repo.list_performance_seats = AsyncMock(return_value=[row()])
        self.repo.list_performance_seat_states = AsyncMock(
            return_value=[dict(perf_seat_id=101, status="RESERVED")]
        )
        self.grades = Mock()
        self.grades.performance_exists = AsyncMock(return_value=True)
        self.service = PerformanceSeatService(self.repo, self.grades, self.cache)

    async def test_miss_reads_database_and_never_stores_status(self):
        self.assertEqual(await self.service.list_performance_seats(10), [row()])
        self.repo.list_performance_seats.assert_awaited_once_with(10)
        args = self.client.set.call_args
        metadata = json.loads(args.args[1])
        self.assertEqual(set(metadata[0]), set(METADATA_FIELDS))
        self.assertNotIn("status", metadata[0])
        self.assertNotIn("reserv_id", metadata[0])
        self.assertEqual(args.kwargs["ex"], 10)

    async def test_hit_reads_current_state_without_full_list_query(self):
        self.client.get.return_value = json.dumps(
            [{field: row()[field] for field in METADATA_FIELDS}]
        )
        self.assertEqual(
            await self.service.list_performance_seats(10), [row("RESERVED")]
        )
        self.repo.list_performance_seats.assert_not_awaited()
        self.repo.list_performance_seat_states.assert_awaited_once_with(10)
        # 해제된 상태도 캐시 삭제 없이 DB에서 다시 읽는다.
        self.repo.list_performance_seat_states.return_value[0]["status"] = "AVAILABLE"
        self.assertEqual(await self.service.list_performance_seats(10), [row()])

    async def test_empty_list_is_a_hit_and_changed_membership_reloads(self):
        self.client.get.return_value = "[]"
        self.repo.list_performance_seat_states.return_value = []
        self.assertEqual(await self.service.list_performance_seats(10), [])
        self.repo.list_performance_seats.assert_not_awaited()
        self.repo.list_performance_seat_states.return_value = [
            dict(perf_seat_id=101, status="AVAILABLE")
        ]
        self.assertEqual(await self.service.list_performance_seats(10), [row()])
        self.repo.list_performance_seats.assert_awaited_once()

    async def test_missing_performance_does_not_return_cache(self):
        self.grades.performance_exists.return_value = False
        with self.assertRaises(PerformanceNotFoundError):
            await self.service.list_performance_seats(10)
        self.client.get.assert_not_awaited()

    async def test_redis_outage_falls_back_and_write_failure_is_ignored(self):
        self.client.get.side_effect = RedisConnectionError("offline")
        self.client.set.side_effect = RedisConnectionError("offline")
        self.assertEqual(await self.service.list_performance_seats(10), [row()])

    async def test_slow_redis_times_out_and_falls_back(self):
        import asyncio

        async def never_returns(key):
            await asyncio.Event().wait()

        self.client.get.side_effect = never_returns
        self.assertEqual(await self.service.list_performance_seats(10), [row()])
        self.repo.list_performance_seats.assert_awaited_once()

    async def test_corrupt_and_wrong_performance_cache_are_misses(self):
        metadata = {field: row()[field] for field in METADATA_FIELDS}
        for value in [
            "not json",
            "null",
            "{}",
            '[{"perf_seat_id":true}]',
            json.dumps([{**metadata, "perf_id": 20}]),
            json.dumps([{**metadata, "status": "AVAILABLE"}]),
            json.dumps([metadata, metadata]),
        ]:
            with self.subTest(value=value):
                self.client.get.return_value = value
                self.assertIsNone(await self.cache.get(10))

    async def test_unusable_source_data_does_not_break_cache_write(self):
        for items in [[{}], [{**row(), "grade": []}], [{**row(), "price": object()}]]:
            with self.subTest(items=items):
                await self.cache.set(10, items)
        self.client.set.assert_not_awaited()

    async def test_unconfigured_cache_opens_no_connection(self):
        with patch.dict(os.environ, {"SEAT_CACHE_REDIS_URL": ""}):
            async with self.provided_cache() as cache:
                self.assertIsNone(cache)

    async def test_invalid_configuration_disables_cache(self):
        with patch.dict(os.environ, {"SEAT_CACHE_REDIS_URL": "invalid://host"}):
            async with self.provided_cache() as cache:
                self.assertIsNone(cache)

    @staticmethod
    def provided_cache():
        from contextlib import asynccontextmanager

        return asynccontextmanager(provide_seat_list_cache)()

    async def test_write_invalidation_happens_after_commit_and_outside_rollback(self):
        saved = SeatInfo(
            seat_id=1, perf_id=10, name=SeatGrade.R, total_seat=1, price=30000
        )
        grade_repo = Mock()
        grade_repo.get_seat_info = AsyncMock(return_value=saved)
        grade_repo.grade_exists = AsyncMock(return_value=False)
        grade_repo.save_seat_info = AsyncMock(return_value=saved)
        grade_repo.rollback = AsyncMock()
        seats_repo = Mock()
        seats_repo.names_exist = AsyncMock(return_value=False)
        seats_repo.save_many = AsyncMock()
        service = SeatInfoService(grade_repo, seats_repo, CatalogPolicy(), self.cache)
        service._authorize = AsyncMock()
        actor = CatalogActor(user_id=7, role="SELLER")
        events = []

        async def commit():
            events.append("commit")

        async def delete(key):
            events.append("invalidate")
            raise RedisConnectionError("offline")

        grade_repo.commit = AsyncMock(side_effect=commit)
        self.client.delete.side_effect = delete
        await service.update_price(10, 1, 50000, actor)
        self.assertEqual(events, ["commit", "invalidate"])
        grade_repo.rollback.assert_not_awaited()
        events.clear()
        await service.create(
            perf_id=10,
            name=SeatGrade.R,
            total_seat=1,
            price=30000,
            seat_seqs=["A01"],
            actor=actor,
        )
        self.assertEqual(events, ["commit", "invalidate"])
        grade_repo.commit.side_effect = RuntimeError("commit failed")
        self.client.delete.reset_mock()
        with self.assertRaises(RuntimeError):
            await service.update_price(10, 1, 50000, actor)
        grade_repo.rollback.assert_awaited_once()
        self.client.delete.assert_not_awaited()


@unittest.skipUnless(
    os.getenv("SEAT_CACHE_TEST_REDIS_URL"), "개인 테스트 Redis 주소 필요"
)
class RealRedisTests(unittest.IsolatedAsyncioTestCase):
    async def test_expiry_and_actual_connection_failure(self):
        import asyncio
        from uuid import uuid4

        perf_id = uuid4().int % 1_000_000_000 + 1
        client = Redis.from_url(
            os.environ["SEAT_CACHE_TEST_REDIS_URL"], decode_responses=True
        )
        self.addAsyncCleanup(client.aclose)
        cache = RedisSeatListCache(client, ttl=1)
        self.addAsyncCleanup(client.delete, cache.key(perf_id))
        await cache.set(perf_id, [row(perf_id=perf_id)])
        self.assertIsNotNone(await cache.get(perf_id))
        await asyncio.sleep(1.1)
        self.assertIsNone(await cache.get(perf_id))
        offline = Redis.from_url("redis://127.0.0.1:1/9", socket_connect_timeout=0.05)
        self.addAsyncCleanup(offline.aclose)
        unavailable = RedisSeatListCache(offline)
        self.assertIsNone(await unavailable.get(perf_id))
        await unavailable.set(perf_id, [row(perf_id=perf_id)])
        await unavailable.invalidate(perf_id)

    async def test_roundtrip_ttl_delete_and_live_database_state(self):
        from uuid import uuid4

        perf_id = uuid4().int % 1_000_000_000 + 1
        client = Redis.from_url(
            os.environ["SEAT_CACHE_TEST_REDIS_URL"], decode_responses=True
        )
        self.addAsyncCleanup(client.aclose)
        cache = RedisSeatListCache(client)
        self.addAsyncCleanup(client.delete, cache.key(perf_id))
        item = row(perf_id=perf_id)
        repo = Mock()
        repo.list_performance_seats = AsyncMock(return_value=[item])
        repo.list_performance_seat_states = AsyncMock(
            return_value=[dict(perf_seat_id=101, status="RESERVED")]
        )
        grades = Mock(performance_exists=AsyncMock(return_value=True))
        service = PerformanceSeatService(repo, grades, cache)
        await service.list_performance_seats(perf_id)
        self.assertNotIn("status", json.loads(await client.get(cache.key(perf_id)))[0])
        self.assertGreater(await client.ttl(cache.key(perf_id)), 0)
        self.assertEqual(
            (await service.list_performance_seats(perf_id))[0]["status"], "RESERVED"
        )
        repo.list_performance_seats.assert_awaited_once()
        await cache.invalidate(perf_id)
        self.assertIsNone(await cache.get(perf_id))
        await service.list_performance_seats(perf_id)
        self.assertEqual(repo.list_performance_seats.await_count, 2)
