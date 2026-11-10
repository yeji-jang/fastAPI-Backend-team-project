"""Narrow show contract, shared request session and lock/transaction ordering.

SQLite executes the writes; PostgreSQL compilation checks the real lock queries.
This does not simulate PostgreSQL row-lock contention.
"""

import unittest
from unittest.mock import AsyncMock, Mock, call, patch

from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql

import test_catalog as fixtures
import asyncticket.main as main_module
from asyncticket.main import create_app
from asyncticket.performances.application.ports import ShowAccess, ShowReference
from asyncticket.performances.application.service import PerformanceApplicationService
from asyncticket.performances.infrastructure.models import PerformanceModel
from asyncticket.performances.infrastructure.repositories import SqlAlchemyPerformanceRepository
from asyncticket.performances.presentation.schemas import PerformanceCreateRequest
from asyncticket.shared.core.database import get_db
from asyncticket.shared.domain.catalog import CatalogActor
from asyncticket.shared.infrastructure.catalog import SqlAlchemyCatalogUnitOfWork


class AppRegistrationTests(unittest.TestCase):
    def test_handlers_are_registered_once_in_order_and_venue_routes_remain(self):
        registrations = Mock()
        with (
            patch.object(main_module, "register_exception_handlers", wraps=main_module.register_exception_handlers) as common,
            patch.object(main_module, "register_catalog_errors", wraps=main_module.register_catalog_errors) as catalog,
            patch.object(main_module, "wire_dependencies", wraps=main_module.wire_dependencies) as wiring,
        ):
            registrations.attach_mock(common, "common")
            registrations.attach_mock(catalog, "catalog")
            registrations.attach_mock(wiring, "wiring")
            app = create_app()

        self.assertEqual(registrations.mock_calls, [call.common(app), call.catalog(app), call.wiring(app)])
        paths = app.openapi()["paths"]
        self.assertTrue({"get", "post", "patch"}.issubset(paths["/v1/venues"]))
        self.assertIn("get", paths["/v1/venues/list"])


class OnlyShowAccess(ShowAccess):
    """A collaborator with the two required methods, without show CRUD methods."""

    __slots__ = ("show", "calls")

    def __init__(self, show):
        self.show = show
        self.calls = []

    async def find_by_id(self, show_id, *, for_update=False):
        self.calls.append("find_by_id")
        return ShowReference(show_id=self.show.show_id)

    async def authorize_owner(self, show_id, actor):
        self.calls.append("authorize_owner")
        return ShowReference(show_id=self.show.show_id)


class TracedSession(fixtures.AsyncSessionAdapter):
    def __init__(self, session):
        super().__init__(session)
        self.events = []

    async def scalar(self, statement):
        self.events.append(("select", str(statement.compile(dialect=postgresql.dialect()))))
        return await super().scalar(statement)

    async def execute(self, statement):
        if statement.is_insert or statement.is_update or statement.is_delete:
            self.events.append(("write", str(statement.compile(dialect=postgresql.dialect()))))
        return await super().execute(statement)

    async def commit(self):
        self.events.append(("commit", ""))
        await super().commit()

    async def rollback(self):
        self.events.append(("rollback", ""))
        await super().rollback()


class PerformanceDependencyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fixture = fixtures.CatalogApiTests()
        self.fixture.setUp()
        self.session = TracedSession(self.fixture.session)
        self.opened = []

        async def request_db():
            self.opened.append(self.session)
            yield self.session

        self.app = create_app(authenticator=fixtures.FixtureAuthenticator())
        self.app.dependency_overrides[get_db] = request_db

    def tearDown(self):
        self.fixture.tearDown()

    def assert_show_locked_before_write(self, final_event, *, performance_lock=False):
        events = self.session.events
        locks = [i for i, (kind, sql) in enumerate(events)
                 if kind == "select" and "FROM shows" in sql and "FOR UPDATE" in sql]
        writes = [i for i, (kind, _) in enumerate(events) if kind == "write"]
        endings = [i for i, (kind, _) in enumerate(events) if kind == final_event]
        self.assertEqual(self.opened, [self.session])
        self.assertEqual(len(locks), 1, events)
        self.assertEqual(len(writes), 1, events)
        self.assertEqual(len(endings), 1, events)
        self.assertLess(locks[0], writes[0])
        self.assertLess(writes[0], endings[0])
        if performance_lock:
            perf_locks = [i for i, (kind, sql) in enumerate(events)
                          if kind == "select" and "FROM performances" in sql and "FOR UPDATE" in sql]
            self.assertEqual(len(perf_locks), 1, events)
            self.assertLess(locks[0], perf_locks[0])
            self.assertLess(perf_locks[0], writes[0])
        other = "rollback" if final_event == "commit" else "commit"
        self.assertFalse(any(kind == other for kind, _ in events), events)

    async def test_minimal_two_method_show_collaborator_supports_performance_operations(self):
        access = OnlyShowAccess(await self.fixture.shows.find_by_id(2))
        service = PerformanceApplicationService(
            SqlAlchemyPerformanceRepository(fixtures.AsyncSessionAdapter(self.fixture.session)),
            access, self.fixture.relations, self.fixture.uow, self.fixture.policy,
        )
        self.assertEqual(await service.find_all(2, None), [])
        actor = CatalogActor(1, "SELLER")
        values = PerformanceCreateRequest.model_validate(self.fixture.performance_body()).model_dump()
        created = await service.create(2, values, actor)
        updated = await service.update(created.perf_id, {"round_number": 8}, actor)
        self.assertEqual(updated.round_number, 8)
        await service.delete(created.perf_id, actor)
        self.assertEqual(access.calls, ["find_by_id", "authorize_owner", "authorize_owner", "authorize_owner"])

    async def test_real_wiring_keeps_show_lock_and_writes_in_one_request_transaction(self):
        status, _, created = await fixtures.catalog_request(
            self.app, "POST", "/v1/shows/2/performances", self.fixture.performance_body(), "seller",
        )
        self.assertEqual(status, 201)
        self.assert_show_locked_before_write("commit")
        perf_id = created["perf_id"]
        for method, body, expected in [("PATCH", {"round_number": 8}, 200), ("DELETE", None, 204)]:
            with self.subTest(method=method):
                self.session.events.clear()
                self.opened.clear()
                status, _, _ = await fixtures.catalog_request(
                    self.app, method, f"/v1/performances/{perf_id}", body, "seller",
                )
                self.assertEqual(status, expected)
                self.assert_show_locked_before_write("commit", performance_lock=True)

    async def test_write_after_show_lock_rolls_back_when_commit_fails(self):
        before = self.fixture.session.scalar(select(func.count()).select_from(PerformanceModel))
        with patch.object(SqlAlchemyCatalogUnitOfWork, "commit", AsyncMock(side_effect=RuntimeError("test commit failure"))):
            status, _, body = await fixtures.asgi_request(
                self.app, "POST", "/v1/shows/2/performances", self.fixture.performance_body(), "seller",
                raise_server_exceptions=False,
            )
        self.assertEqual(status, 500)
        self.assertEqual(body["code"], "INTERNAL_SERVER_ERROR")
        self.assert_show_locked_before_write("rollback")
        self.assertEqual(self.fixture.session.scalar(select(func.count()).select_from(PerformanceModel)), before)
