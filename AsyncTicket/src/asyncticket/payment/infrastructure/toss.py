"""토스페이먼츠 결제 승인·취소 호출 (PaymentProcess 구현)

- 인증: Basic base64("<시크릿 키>:")
- 멱등키: POST 요청에만 의미가 있고 15일간 유효. 같은 키로 다시 보내면 첫 응답을 그대로 돌려준다.
    승인: confirm-<paymentKey>  (같은 orderId로 결제창을 다시 열면 paymentKey가 달라 새 요청으로 처리)
    취소: cancel-<paymentKey>   (전액 환불 1회)

<호출하는 토스 API>
    1) 결제 승인 : POST https://api.tosspayments.com/v1/payments/confirm
    2) 결제 취소 : POST https://api.tosspayments.com/v1/payments/{paymentKey}/cancel

<실패 처리> (PaymentGatewayException)
    - 시크릿 키 없음        → 호출하지 않고 502 (TOSS_SECRET_KEY_MISSING)
    - 연결 실패·시간 초과   → 502 (TOSS_UNREACHABLE). 토스에서 처리됐는지 알 수 없어 대조가 필요하다
    - 토스가 4xx로 거절     → 400 + 토스 코드 (예: TOSS_REJECT_CARD_PAYMENT)
    - 토스 5xx              → 502

<환경 변수>
    - TOSS_SECRET_KEY : 토스 개별 연동 시크릿 키 (test_sk_...). 코드·커밋에 넣지 않고 .env에만 둔다
"""

# <표준 라이브러리>
import base64
import os
from decimal import Decimal
from typing import Any

# <외부 라이브러리>
import httpx
from dotenv import load_dotenv
from fastapi import status

# <Domain - 결제>
from asyncticket.payment.domain.exceptions import PaymentGatewayException # 토스 호출 실패
from asyncticket.payment.domain.payment_log import PaymentLog # 토스 응답 1건
from asyncticket.payment.domain.service import PaymentProcess # (추상)토스 호출 약속

# <Shared>
from asyncticket.shared.core.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

# 1. 토스 결제 API 기본 주소
TOSS_PAYMENTS_URL = "https://api.tosspayments.com/v1/payments"


# 2. 토스 호출 구현
class TossPaymentProcess(PaymentProcess):
    def __init__(
        self,
        secret_key: str | None = None,
        *,
        base_url: str = TOSS_PAYMENTS_URL,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,  # 테스트에서 MockTransport 주입
    ):
        self._secret_key = secret_key if secret_key is not None else os.getenv("TOSS_SECRET_KEY")
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout             # 초 단위. 넘으면 TOSS_UNREACHABLE
        self._transport = transport

    # 1) 결제 승인
    async def approve(self, *, payment_key: str, order_id: str, amount: Decimal) -> PaymentLog:
        body = {"paymentKey": payment_key, "orderId": order_id, "amount": _won(amount)}
        return await self._post("/confirm", body, idempotency_key=f"confirm-{payment_key}")

    # 2) 결제 취소 (전액 환불)
    async def cancel(self, *, payment_key: str, reason: str) -> PaymentLog:
        body = {"cancelReason": reason}
        return await self._post(f"/{payment_key}/cancel", body, idempotency_key=f"cancel-{payment_key}")

    # 3) 공통 헤더 (인증 + 멱등키)
    def _headers(self, idempotency_key: str) -> dict[str, str]:
        if not self._secret_key:
            raise PaymentGatewayException(
                "토스 시크릿 키(TOSS_SECRET_KEY)가 설정되지 않았습니다.",
                error_code="TOSS_SECRET_KEY_MISSING",
            )
        token = base64.b64encode(f"{self._secret_key}:".encode("utf-8")).decode("ascii")
        return {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
        }

    # 4) 공통 POST 요청 + 실패 처리
    async def _post(self, path: str, body: dict[str, Any], *, idempotency_key: str) -> PaymentLog:
        headers = self._headers(idempotency_key)
        url = f"{self._base_url}{path}"
        # 4-1) 요청 보내기 (연결 실패·시간 초과)
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            try:
                res = await client.post(url, json=body, headers=headers)
            except httpx.RequestError as e:
                # 시간 초과 포함: 토스에서 처리됐는지 알 수 없으므로 대조가 필요하다
                logger.error(f"[토스 연결 실패] {path} {type(e).__name__}: {e}")
                raise PaymentGatewayException("토스 결제 서버에 연결하지 못했습니다.", error_code="TOSS_UNREACHABLE") from e

        # 4-2) 토스가 거절 (4xx → 400, 5xx → 502)
        if res.is_error:
            try:
                data = res.json()
                code = str(data.get("code", f"HTTP_{res.status_code}"))
                message = str(data.get("message", "토스 결제 요청이 거절되었습니다."))
            except ValueError:
                code, message = f"HTTP_{res.status_code}", "토스 결제 요청이 거절되었습니다."
            logger.error(f"[토스 요청 실패] {path} status={res.status_code} code={code} message={message}")
            http_status = status.HTTP_400_BAD_REQUEST if res.status_code < 500 else status.HTTP_502_BAD_GATEWAY
            raise PaymentGatewayException(message, error_code=f"TOSS_{code}", status_code=http_status)

        # 4-3) 성공 응답을 그대로 기록으로 돌려준다
        return PaymentLog(value=res.json())


# 3. 금액 변환 : Decimal → 원 단위 정수
def _won(amount: Decimal) -> int:
    """토스 금액은 원 단위 정수다. 소수점이 있으면 보내지 않는다."""
    value = Decimal(amount)
    if value != value.to_integral_value():
        raise PaymentGatewayException("결제 금액은 원 단위 정수여야 합니다.", error_code="INVALID_AMOUNT", status_code=status.HTTP_400_BAD_REQUEST)
    return int(value)
