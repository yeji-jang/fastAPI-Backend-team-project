"""화면 조립이 팀 API 계약을 바꾸거나 비밀 설정을 노출하지 않는지 검사한다."""

import os
import unittest
from unittest.mock import patch

import httpx

from asyncticket.main import create_app


class FrontendTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = create_app()
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://test",
        )
        self.addAsyncCleanup(self.client.aclose)

    async def test_all_pages_and_assets_render_without_database_calls(self):
        pages = [
            "/",
            "/login",
            "/signup",
            "/me",
            "/venues",
            "/venues/1",
            "/shows",
            "/shows/1",
            "/performances/1",
            "/manage",
            "/manage/edit",
            "/reservations",
            "/me/reservations",
            "/checkout/1",
            "/payment/success",
            "/payment/fail",
        ]
        for path in pages:
            with self.subTest(path=path):
                response = await self.client.get(path)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertNotIn("/reservations/check", response.text)
        for path in [
            "style.css",
            "account.js",
            "booking.js",
            "my_reservations.js",
            "my_reservations.css",
            "app.js",
            "after-hours.jpg",
        ]:
            response = await self.client.get("/venue-assets/" + path)
            self.assertEqual(response.status_code, 200)

    async def test_frontend_does_not_change_team_api_schema(self):
        paths = self.app.openapi()["paths"]
        for path in ["/v1/shows", "/v1/reservations", "/v1/payments", "/v1/payments/approve"]:
            self.assertIn(path, paths)
        self.assertNotIn("/web/config", paths)
        self.assertNotIn("/login", paths)

    async def test_config_never_exposes_a_secret_key(self):
        for value in ["", "test_sk_fake_secret", "live_sk_fake_secret"]:
            with self.subTest(value=value), patch.dict(
                os.environ,
                {"TOSS_CLIENT_KEY": value, "TOSS_SECRET_KEY": "must_not_be_public"},
            ):
                response = await self.client.get("/web/config")
                self.assertEqual(response.json(), {"toss_client_key": None})
                self.assertNotIn("must_not_be_public", response.text)
                self.assertEqual(response.headers["cache-control"], "no-store")
        with patch.dict(os.environ, {"TOSS_CLIENT_KEY": "test_ck_public_example"}):
            response = await self.client.get("/web/config")
            self.assertEqual(
                response.json()["toss_client_key"], "test_ck_public_example"
            )

    async def test_invalid_page_ids_return_422(self):
        for path in ["/shows/0", "/venues/-1", "/checkout/not-an-id"]:
            self.assertEqual((await self.client.get(path)).status_code, 422)
