import os
import base64
from dotenv import load_dotenv
from payment.domain.service import PaymentProcess
import httpx
from payment.domain.exceptions import PaymentException
from shared.core.logger import get_logger

logger = get_logger(__file__)

load_dotenv()

secret_key = load_dotenv("TOSS_SECRET_KEY", "test_sk_zXLkKEypNArWmo50nX3lmeaxYG5R")
toss_api_key = os.getenv("toss_api_key")


class TossPaymentProcess(PaymentProcess):
    def __init__(self):
        # API 기본 요청 주소
        self.base_url="https://api.tosspayments.con/v1/payments"


    def _get_headers(self,reserv_id: int):
        key = f"{secret_key}:".encode("utf-8")
        idempotency_key = str(reserv_id).encode("utf-8") # 멱등성 키
        return {
            "Authorization": f"{base64.b64encode(secret_key)}",
            "Content-Type": "application/json",
            "Idempotency-Key": base64.b64encode(idempotency_key).decode("utf-8")
        }

    async def approve(self, payment_key: str, reserv_id: int, amount: int) -> PaymentLog:
        """결제 승인 처리"""
        headers = self._get_headers(reserv_id)

        async with https.AsyncClient() as client:
            async def callback():
                res = await client.post(
                    url = f"{self.base_url}confirm",
                    headers = headers
                    json = {
                        "paymentKey": payment_key
                        "orderID": reserv_id,
                        "amount": amount
                        }
                )
                res.raise_for_status() # 2xx,3xx 외의 응답 코드는 예외를 던진다.
                return res.json()
            return self._request_wrapper(callback)
        
    async def cancel(self, payment_key: str, reserv_id: int, reason: str) -> PaymentLog:
        """결제 취소 처리"""
        headers = self._get_headers(reserv_id)
        
        async with https.AsyncClient() as client:
            async def callback():
                res = await client.post(
                    url = f"{self.base_url}{payment_key}/cancel",
                    headers = headers
                    json = {"cancelReason": reason}
                )
                res.raise_for_status() # 2xx,3xx 외의 응답 코드는 예외를 던진다.
                return res.json()
            return self._request_wrapper(callback)



    # 데코레이터 안 되서 콜백, 반복되는 거 호출
    async def _request_wrapper(callback):
            try:
                return await callback()
            except httx.HTTPStatusError as e:
                try:
                    err_data = e.response.json()
                    code = err_data.get("code", "UNKNOWN_ERROR")
                    message = err_data.get("message", e.response.text)

                except ValueError:
                    code = f"HTTP_{exc.response.status_code}"
                    message = exc.response.text

                logger.error(f"토스 결제 승인 실패 - 코드: {code}, 사유: {message}")

                raise
            except httpx.RequestError as e:
                logger.error(f"토스 API 호출 에러 - 요청 주소: {e.request.url}, 사유: {str(e)}")
                raise
