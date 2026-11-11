"""공용 앱 조립과 수명주기 회귀 검사. DB 작업은 모두 대역으로 확인한다."""

import unittest
from importlib import import_module
from unittest.mock import AsyncMock, MagicMock, patch

from asyncticket.shared.domain.catalog import CatalogPolicy

main = import_module("asyncticket.main")


class AppInitializationTests(unittest.IsolatedAsyncioTestCase):
    def test_app_construction_does_not_run_database_startup(self) -> None:
        # 문서 조회용 앱 생성·테스트 구성이 실제 DB 시작 작업을 실행하면 안 된다.
        with patch.object(main, "init_models") as init_models, patch.object(main, "engine") as engine:
            app = main.create_app()
        init_models.assert_not_called()
        engine.begin.assert_not_called()
        self.assertIsNone(app.state.catalog_authenticator)

    def test_configuration_is_injected_and_isolated_between_apps(self) -> None:
        authenticator = MagicMock()
        policy = CatalogPolicy(admin_can_manage_all=False)
        configured = main.create_app(authenticator=authenticator, policy=policy)
        default_one = main.create_app()
        default_two = main.create_app()

        self.assertIs(configured.state.catalog_authenticator, authenticator)
        self.assertIs(configured.state.catalog_policy, policy)
        self.assertIsNone(default_one.state.catalog_authenticator)
        self.assertIsNot(default_one.state.catalog_policy, default_two.state.catalog_policy)
        self.assertTrue(default_one.state.catalog_policy.admin_can_manage_all)

    def test_merged_app_exposes_catalog_venue_auth_and_user_routes(self) -> None:
        paths = main.create_app().openapi()["paths"]
        for path in (
            "/v1/shows", "/v1/performances/{perf_id}",
            "/v1/venues", "/v1/auth/login", "/v1/users",
        ):
            with self.subTest(path=path):
                self.assertIn(path, paths)
        self.assertIn("post", paths["/v1/users"])
        self.assertIn("post", paths["/v1/auth/login"])

    def test_exception_registrations_and_wiring_run_once(self) -> None:
        with (
            patch.object(main, "register_exception_handlers") as common,
            patch.object(main, "register_catalog_errors") as catalog,
            patch.object(main, "wire_dependencies") as wiring,
        ):
            app = main.create_app()
        common.assert_called_once_with(app)
        catalog.assert_called_once_with(app)
        wiring.assert_called_once_with(app)

    async def test_lifespan_preserves_model_and_schema_startup_then_closes_pool(self) -> None:
        connection = MagicMock()
        connection.run_sync = AsyncMock()
        transaction = MagicMock()
        transaction.__aenter__ = AsyncMock(return_value=connection)
        transaction.__aexit__ = AsyncMock(return_value=False)
        engine = MagicMock()
        engine.begin.return_value = transaction
        app = main.create_app()

        with (
            patch.object(main, "init_models") as init_models,
            patch.object(main, "engine", engine),
            patch.object(main, "close_db", new_callable=AsyncMock) as close_db,
        ):
            async with app.router.lifespan_context(app):
                init_models.assert_called_once_with()
                engine.begin.assert_called_once_with()
                connection.run_sync.assert_awaited_once_with(main.Base.metadata.create_all)
                close_db.assert_not_awaited()
            close_db.assert_awaited_once_with()

    async def test_startup_failures_propagate_and_still_close_pool(self) -> None:
        for stage in ("model_registration", "schema_creation"):
            with self.subTest(stage=stage):
                failure = RuntimeError("startup failed")
                connection = MagicMock()
                connection.run_sync = AsyncMock(
                    side_effect=failure if stage == "schema_creation" else None
                )
                transaction = MagicMock()
                transaction.__aenter__ = AsyncMock(return_value=connection)
                transaction.__aexit__ = AsyncMock(return_value=False)
                engine = MagicMock()
                engine.begin.return_value = transaction

                with (
                    patch.object(main, "init_models", side_effect=(
                        failure if stage == "model_registration" else None
                    )),
                    patch.object(main, "engine", engine),
                    patch.object(main, "close_db", new_callable=AsyncMock) as close_db,
                ):
                    app = main.create_app()
                    with self.assertRaisesRegex(RuntimeError, "startup failed"):
                        async with app.router.lifespan_context(app):
                            self.fail("startup failure must not reach request handling")
                    close_db.assert_awaited_once_with()

    async def test_shutdown_closes_pool_when_request_handling_raises(self) -> None:
        connection = MagicMock()
        connection.run_sync = AsyncMock()
        transaction = MagicMock()
        transaction.__aenter__ = AsyncMock(return_value=connection)
        transaction.__aexit__ = AsyncMock(return_value=False)
        engine = MagicMock()
        engine.begin.return_value = transaction

        with (
            patch.object(main, "init_models"),
            patch.object(main, "engine", engine),
            patch.object(main, "close_db", new_callable=AsyncMock) as close_db,
        ):
            app = main.create_app()
            with self.assertRaisesRegex(RuntimeError, "request handling failed"):
                async with app.router.lifespan_context(app):
                    raise RuntimeError("request handling failed")
            close_db.assert_awaited_once_with()
