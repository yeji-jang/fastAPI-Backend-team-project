"""공개 GET 캐시의 HTTP 계약·격리·무효화 검사. 격리 SQLite만 사용한다."""

import asyncio
import unittest
from datetime import timedelta
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi_cache import FastAPICache
from asyncticket.shows.presentation.router import router as show_router
from sqlalchemy import delete, event, update

import test_catalog as fixtures
import asyncticket.main as main
from asyncticket.shows.application.service import ShowApplicationService
from asyncticket.shows.infrastructure.models import ShowModel
from asyncticket.wiring.shows import provide_show_service


class CatalogCacheTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        # TestCase를 상속하지 않고 fixture만 합성해 기존 테스트의 중복 수집을 피한다.
        self.fixture = fixtures.CatalogApiTests(methodName="runTest")
        self.fixture.setUp()
        self.app = self.fixture.app
        self.shows = self.fixture.shows
        self.performances = self.fixture.performances
        self.selects = {"shows": 0, "performances": 0}

        @event.listens_for(self.fixture.engine, "before_cursor_execute")
        def count_selects(connection, cursor, statement, parameters, context, executemany):
            normalized = " ".join(statement.lower().split())
            if normalized.startswith("select"):
                for table in self.selects:
                    if f"from {table}" in normalized:
                        self.selects[table] += 1

    async def asyncSetUp(self) -> None:
        main.init_catalog_cache(self.app)

    async def asyncTearDown(self) -> None:
        await main.clear_catalog_cache(self.app)

    def tearDown(self) -> None:
        self.fixture.tearDown()

    async def request(self, method, path, body=None, token=None, *, app=None):
        return await fixtures.asgi_request(app or self.app, method, path, body, token)

    async def data(self, path, *, app=None):
        status, _, envelope = await self.request("GET", path, app=app)
        self.assertEqual(status, 200, envelope)
        return envelope["data"]

    async def test_router_without_cache_lifespan_keeps_original_get_behavior(self):
        app = FastAPI()
        app.include_router(show_router)
        app.dependency_overrides.update(self.app.dependency_overrides)
        first = await self.data("/v1/shows/1", app=app)
        second = await self.data("/v1/shows/1", app=app)
        self.assertEqual(first, second)
        self.assertEqual(self.selects["shows"], 2)

    async def test_warm_show_detail_reuses_data_but_builds_fresh_envelope(self):
        with patch("asyncticket.shared.core.schemas.datetime") as clock:
            clock.now.side_effect = [fixtures.T0, fixtures.T0 + timedelta(seconds=1)]
            status, _, first = await self.request("GET", "/v1/shows/1")
            second_status, _, second = await self.request("GET", "/v1/shows/1")
        self.assertEqual((status, second_status), (200, 200))
        self.assertEqual(first["data"], second["data"])
        self.assertNotEqual(first["responded_at"], second["responded_at"])
        self.assertEqual(self.selects["shows"], 1)
        self.assertEqual(set(second), {
            "success", "code", "message", "errors", "data", "responded_at",
        })
        self.assertEqual(second["code"], "OK")

    async def test_warm_hit_survives_new_service_instance_for_each_request(self):
        built = []

        def new_service():
            service = ShowApplicationService(
                self.shows._repository, self.fixture.relations,
                self.fixture.uow, self.fixture.policy,
            )
            built.append(service)
            return service

        self.app.dependency_overrides[provide_show_service] = new_service
        first = await self.data("/v1/shows/1")
        second = await self.data("/v1/shows/1")
        self.assertEqual(first, second)
        self.assertEqual(len(built), 2)
        self.assertIsNot(built[0], built[1])
        self.assertEqual(self.selects["shows"], 1)

    async def test_detail_ids_do_not_share_cache_entries(self):
        for path, key, expected in (
            ("/v1/shows/1", "show_id", 1),
            ("/v1/shows/2", "show_id", 2),
            ("/v1/performances/10", "perf_id", 10),
            ("/v1/performances/11", "perf_id", 11),
        ):
            with self.subTest(path=path):
                self.assertEqual((await self.data(path))[key], expected)
                self.assertEqual((await self.data(path))[key], expected)
        self.assertEqual(self.selects, {"shows": 2, "performances": 2})

    async def test_show_list_cache_separates_every_query_condition(self):
        cases = (
            ("", [3, 2, 1], 3),
            ("?page=2&size=1", [2], 3),
            ("?keyword=Beta", [2], 1),
            ("?keyword=Alpha", [3, 1], 2),
            ("?type=CONCERT", [3, 1], 2),
            ("?type=CLASS", [2], 1),
            ("?venues_id=1", [3, 1], 2),
            ("?venues_id=2", [2], 1),
        )
        with patch.object(self.shows, "find_all", wraps=self.shows.find_all) as read:
            for query, expected_ids, total in cases:
                with self.subTest(query=query):
                    first = await self.data("/v1/shows" + query)
                    second = await self.data("/v1/shows" + query)
                    self.assertEqual([row["show_id"] for row in first["items"]], expected_ids)
                    self.assertEqual(first["total"], total)
                    self.assertEqual(first, second)
            self.assertEqual(read.await_count, len(cases))

    async def test_performance_list_cache_separates_kst_dates_and_parent_ids(self):
        cases = (
            ("/v1/shows/1/performances", [10, 11, 12, 13]),
            ("/v1/shows/1/performances?date=2026-11-02", [10]),
            ("/v1/shows/1/performances?date=2026-11-03", [11, 12]),
            ("/v1/shows/1/performances?date=2026-11-04", [13]),
            ("/v1/shows/2/performances", []),
        )
        with patch.object(self.performances, "find_all", wraps=self.performances.find_all) as read:
            for path, expected in cases:
                with self.subTest(path=path):
                    first = await self.data(path)
                    second = await self.data(path)
                    self.assertEqual([row["perf_id"] for row in first["items"]], expected)
                    self.assertEqual(first, second)
            self.assertEqual(read.await_count, len(cases))

    async def test_all_four_get_caches_expire_without_real_sleep(self):
        for path, owner, method, seconds in (
            ("/v1/shows/1", self.shows, "find_by_id", 60),
            ("/v1/shows", self.shows, "find_all", 30),
            ("/v1/performances/10", self.performances, "find_by_id", 10),
            ("/v1/shows/1/performances", self.performances, "find_all", 10),
        ):
            with self.subTest(path=path):
                await main.invalidate_catalog_cache(self.app, "shows", "performances")
                with (
                    patch("fastapi_cache.backends.inmemory.time.time", return_value=1000) as clock,
                    patch.object(owner, method, wraps=getattr(owner, method)) as read,
                ):
                    first = await self.data(path)
                    clock.return_value = 1000 + seconds - 1
                    self.assertEqual(await self.data(path), first)
                    self.assertEqual(read.await_count, 1)
                    clock.return_value = 1000 + seconds + 1
                    self.assertEqual(await self.data(path), first)
                    self.assertEqual(read.await_count, 2)

    async def test_show_update_invalidates_detail_and_filtered_lists(self):
        await self.data("/v1/shows/1")
        await self.data("/v1/shows?keyword=Alpha")
        status, _, result = await self.request(
            "PATCH", "/v1/shows/1", {"title": "Changed title"}, "seller",
        )
        self.assertEqual(status, 200, result)
        self.assertEqual((await self.data("/v1/shows/1"))["title"], "Changed title")
        remaining = await self.data("/v1/shows?keyword=Alpha")
        self.assertEqual([row["show_id"] for row in remaining["items"]], [3])

    async def test_show_create_and_delete_invalidate_list_and_detail(self):
        await self.data("/v1/shows")
        body = {"venues_id": 1, "title": "Cache create", "type": "CONCERT"}
        status, headers, result = await self.request("POST", "/v1/shows", body, "seller")
        self.assertEqual(status, 201, result)
        show_id = result["data"]["show_id"]
        path = f"/v1/shows/{show_id}"
        self.assertEqual(headers[b"location"].decode(), path)
        self.assertEqual((await self.data("/v1/shows"))["total"], 4)
        await self.data(path)
        status, _, result = await self.request("DELETE", path, token="seller")
        self.assertEqual((status, result), (204, None))
        status, _, result = await self.request("GET", path)
        self.assertEqual(status, 404, result)
        self.assertEqual((await self.data("/v1/shows"))["total"], 3)

    async def test_performance_create_update_delete_invalidate_lists_and_detail(self):
        await self.data("/v1/shows/1/performances")
        status, headers, result = await self.request(
            "POST", "/v1/shows/1/performances", self.fixture.performance_body(), "seller",
        )
        self.assertEqual(status, 201, result)
        perf_id = result["data"]["perf_id"]
        path = f"/v1/performances/{perf_id}"
        self.assertEqual(headers[b"location"].decode(), path)
        self.assertEqual(len((await self.data("/v1/shows/1/performances"))["items"]), 5)
        await self.data(path)
        status, _, result = await self.request("PATCH", path, {"status": "CANCELED"}, "seller")
        self.assertEqual(status, 200, result)
        self.assertEqual((await self.data(path))["status"], "CANCELED")
        listed = await self.data("/v1/shows/1/performances")
        self.assertEqual(next(row for row in listed["items"] if row["perf_id"] == perf_id)["status"], "CANCELED")
        status, _, result = await self.request("DELETE", path, token="seller")
        self.assertEqual((status, result), (204, None))
        status, _, result = await self.request("GET", path)
        self.assertEqual(status, 404, result)
        self.assertEqual(len((await self.data("/v1/shows/1/performances"))["items"]), 4)

    async def test_failed_write_preserves_warm_cache_and_business_authorization(self):
        first = await self.data("/v1/shows/1")
        status, _, result = await self.request(
            "PATCH", "/v1/shows/1", {"title": "Forbidden change"}, "other",
        )
        self.assertEqual(status, 403, result)
        count = self.selects["shows"]
        self.assertEqual(await self.data("/v1/shows/1"), first)
        self.assertEqual(self.selects["shows"], count)

    async def test_performance_list_hit_still_requires_existing_parent(self):
        self.assertEqual((await self.data("/v1/shows/3/performances"))["items"], [])
        # 의도적으로 무효화를 우회해 hit 시 부모 존재 검사가 남는지 확인한다.
        self.fixture.session.execute(delete(ShowModel).where(ShowModel.show_id == 3))
        self.fixture.session.commit()
        status, _, result = await self.request("GET", "/v1/shows/3/performances")
        self.assertEqual(status, 404, result)

    async def test_apps_are_isolated_and_clearing_one_keeps_the_other_warm(self):
        second = fixtures.CatalogApiTests(methodName="runTest")
        second.setUp()
        try:
            second.session.execute(update(ShowModel).where(ShowModel.show_id == 1).values(title="Second app"))
            second.session.commit()
            main.init_catalog_cache(second.app)
            with patch.object(second.shows, "find_by_id", wraps=second.shows.find_by_id) as read:
                self.assertEqual((await self.data("/v1/shows/1"))["title"], "Alpha 100%_Live")
                self.assertEqual((await self.data("/v1/shows/1", app=second.app))["title"], "Second app")
                await main.clear_catalog_cache(self.app)
                self.assertEqual((await self.data("/v1/shows/1", app=second.app))["title"], "Second app")
                self.assertEqual(read.await_count, 1)
        finally:
            await main.clear_catalog_cache(second.app)
            second.tearDown()

    async def test_clear_failure_does_not_fail_commit_or_reuse_old_generation(self):
        await self.data("/v1/shows/1")
        with patch.object(FastAPICache.get_backend(), "clear", new=AsyncMock(side_effect=RuntimeError("cache unavailable"))):
            status, _, result = await self.request(
                "PATCH", "/v1/shows/1", {"title": "Committed title"}, "seller",
            )
        self.assertEqual(status, 200, result)
        self.assertEqual((await self.data("/v1/shows/1"))["title"], "Committed title")

    async def test_late_old_read_cannot_repopulate_current_generation(self):
        loaded = asyncio.Event()
        release = asyncio.Event()
        original = self.shows.find_by_id
        paused = False

        async def delayed_read(show_id, *, for_update=False):
            nonlocal paused
            value = await original(show_id, for_update=for_update)
            if not for_update and not paused:
                paused = True
                loaded.set()
                await release.wait()
            return value

        with patch.object(self.shows, "find_by_id", side_effect=delayed_read):
            pending = asyncio.create_task(self.data("/v1/shows/1"))
            try:
                async with asyncio.timeout(2):
                    await loaded.wait()
                status, _, result = await self.request(
                    "PATCH", "/v1/shows/1", {"title": "Newest title"}, "seller",
                )
                self.assertEqual(status, 200, result)
            finally:
                release.set()
                await pending
        self.assertEqual((await self.data("/v1/shows/1"))["title"], "Newest title")
