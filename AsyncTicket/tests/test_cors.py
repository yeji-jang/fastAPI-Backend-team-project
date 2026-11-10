"""최종 오류 응답과 사전 요청에 대한 CORS 회귀 검사."""
import unittest
import httpx
from fastapi import HTTPException
from asyncticket.main import create_app

ORIGIN = "https://asyncticket.teamsparta.xyz"


class CorsTests(unittest.IsolatedAsyncioTestCase):
    async def test_response_headers_and_error_body(self):
        app = create_app()

        @app.get("/cors-probe/{case}")
        async def probe(case: int):
            if case == 500:
                raise RuntimeError("private error details")
            if case == 401:
                raise HTTPException(status_code=401, detail="unauthorized")
            return {"ok": True}

        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            for case, status in [(200, 200), (401, 401), (500, 500), ("invalid", 422)]:
                with self.subTest(case=case):
                    response = await client.get(f"/cors-probe/{case}", headers={"Origin": ORIGIN})
                    self.assertEqual(response.status_code, status)
                    self.assertEqual(response.headers.get("access-control-allow-origin"), ORIGIN)
                    if status == 500:
                        self.assertEqual(response.json()["code"], "INTERNAL_SERVER_ERROR")
                        self.assertNotIn("private error details", response.text)
            response = await client.options("/cors-probe/200", headers={
                "Origin": ORIGIN, "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["access-control-allow-origin"], ORIGIN)
            response = await client.get("/cors-probe/500", headers={"Origin": "https://unrelated.example"})
            self.assertEqual(response.status_code, 500)
            self.assertNotIn("access-control-allow-origin", response.headers)
