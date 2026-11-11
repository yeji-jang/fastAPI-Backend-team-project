"""팀 DB·main.py를 불러오지 않는 공통 틀 검사. 기존 담당자의 모델 오류와 분리한다."""
import ast
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field

from asyncticket.shared.core.exception_handlers import register_exception_handlers
from asyncticket.shared.core.exceptions import (
    BadRequestException, UnauthorizedException, ForbiddenException, NotFoundException,
    ConflictException, ValidationException,
)
from asyncticket.shared.core.schemas import APIResponse


class SeatResult(BaseModel):
    perf_seat_id: int


class SeatInput(BaseModel):
    total_seat: int = Field(gt=0)


class SeatMissing(NotFoundException):
    pass


class CommonApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FastAPI()
        register_exception_handlers(self.app)

        @self.app.get('/success', response_model=APIResponse[SeatResult])
        async def success():
            return APIResponse[SeatResult].ok(SeatResult(perf_seat_id=11))

        kinds = {400: BadRequestException, 401: UnauthorizedException, 403: ForbiddenException,
                 404: NotFoundException, 409: ConflictException}

        @self.app.get('/business/{code}')
        async def business(code: int):
            raise kinds[code]("공개 안내")

        @self.app.post('/validate')
        async def validate(body: SeatInput):
            return APIResponse[SeatInput].ok(body)

        @self.app.get('/field-error')
        async def field_error():
            raise ValidationException(field_errors={"price": ["음수 가격 불가"]})

        @self.app.get('/http')
        async def http():
            raise HTTPException(401, detail="인증 필요", headers={"WWW-Authenticate": 'Bearer realm="test"', "X-Reason": "expired"})

        @self.app.get('/seat-missing')
        async def seat_missing():
            raise SeatMissing("좌석을 찾을 수 없습니다.", error_code="SEAT_NOT_FOUND")

        @self.app.get('/crash')
        async def crash():
            raise RuntimeError("INTERNAL_MARKER_DO_NOT_EXPOSE")

        self.client = AsyncClient(transport=ASGITransport(app=self.app, raise_app_exceptions=False), base_url='http://test')

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_typed_success_and_utc_timestamp(self):
        r = await self.client.get('/success')
        self.assertEqual(r.status_code, 200)
        dto = APIResponse[SeatResult].model_validate(r.json())
        self.assertEqual(dto.data.perf_seat_id, 11)
        self.assertTrue(dto.success)
        self.assertIsNone(dto.errors)
        self.assertEqual(dto.responded_at.utcoffset(), timedelta(0))

    async def test_business_statuses(self):
        for code in (400, 401, 403, 404, 409):
            with self.subTest(code=code):
                r = await self.client.get(f'/business/{code}')
                self.assertEqual(r.status_code, code)
                self.assertFalse(r.json()['success'])
                self.assertIsNone(r.json()['data'])

    async def test_request_validation_does_not_echo_input(self):
        r = await self.client.post('/validate', json={'total_seat': 'PRIVATE_INPUT_MARKER'})
        self.assertEqual(r.status_code, 422)
        self.assertIn('total_seat', r.json()['errors'])
        self.assertNotIn('PRIVATE_INPUT_MARKER', r.text)
        self.assertNotIn('ctx', r.text)

    async def test_domain_field_errors(self):
        r = await self.client.get('/field-error')
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()['errors'], {'price': ['음수 가격 불가']})

    async def test_http_exception_preserves_headers(self):
        r = await self.client.get('/http')
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.headers['www-authenticate'], 'Bearer realm="test"')
        self.assertEqual(r.headers['x-reason'], 'expired')
        self.assertEqual(r.json()['detail'], '인증 필요')

    async def test_framework_404_keeps_fastapi_default(self):
        r = await self.client.get('/does-not-exist')
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json(), {'detail': 'Not Found'})

    async def test_domain_subclass_uses_common_handler_without_mapping(self):
        r = await self.client.get('/seat-missing')
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()['code'], 'SEAT_NOT_FOUND')

    async def test_unexpected_exception_is_logged_and_masked(self):
        with patch('asyncticket.shared.core.exception_handlers.logger.exception') as log:
            r = await self.client.get('/crash')
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.json()['code'], 'INTERNAL_SERVER_ERROR')
        self.assertNotIn('INTERNAL_MARKER', r.text)
        log.assert_called_once()
        self.assertIsInstance(log.call_args.args[-1], RuntimeError)

    def test_bad_request_can_carry_tutor_error_details(self):
        error = BadRequestException("요청 확인", errors={"seat": ["선택 필요"]})
        response = APIResponse.fail(message=error.message, errors=error.errors)
        self.assertEqual(response.model_dump()["errors"], {"seat": ["선택 필요"]})

    def test_registration_uses_common_exception_base(self):
        from asyncticket.shared.core.exceptions import SharedException
        self.assertIn(SharedException, self.app.exception_handlers)
        self.assertNotIn(SeatMissing, self.app.exception_handlers)


if __name__ == '__main__':
    unittest.main()
