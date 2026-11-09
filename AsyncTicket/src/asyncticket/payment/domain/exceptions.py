"""
<결제 예외>
- 팀 공통 예외(shared/core/exceptions.py)를 상속한다
    → 팀 공통 처리기가 status_code·error_code를 보고 APIResponse 실패 응답으로 바꾼다
- message에는 사용자에게 보여줄 문장, error_code에는 오류를 구분할 업무 코드를 넣는다
"""

# <FastAPI>
from fastapi import status # HTTP 상태 코드 (502)

# <Shared - 팀 공통 예외>
from asyncticket.shared.core.exceptions import (
    BadRequestException,    # 400
    ConflictException,      # 409
    NotFoundException,      # 404
    SharedException,        # 공통 부모 (상태 코드를 직접 정할 때)
)


# 1. 요청 값이 결제 규칙에 맞지 않음 (400)
class PaymentException(BadRequestException[None]):
    """
    결제 예외의 공통 부모
    - paymentKey 없음, 취소 사유 없음 등
    - 바뀔 HTTP 상태 : 400
    """
    def __init__(self, message: str, error_code: str = "PAYMENT_ERROR"):
        super().__init__(message, error_code=error_code)


class PaymentAmountInvalidException(PaymentException):
    """
    결제 금액이 서버의 결제 금액(= 예매 금액)과 다름 → 변조로 보고 토스를 호출하지 않는다
    - 바뀔 HTTP 상태 : 400
    """
    def __init__(self, message: str = "결제 금액이 예매 금액과 다릅니다."):
        super().__init__(message, error_code="PAYMENT_AMOUNT_MISMATCH")


class InvalidOrderIdException(PaymentException):
    """
    주문번호(orderId)가 이 서버가 만든 형식("<접두어>-<reserv_id>")이 아님
    - 바뀔 HTTP 상태 : 400
    """
    def __init__(self, message: str = "주문번호 형식이 올바르지 않습니다."):
        super().__init__(message, error_code="INVALID_ORDER_ID")


# 2. 현재 상태에서는 할 수 없음 (409)
class PaymentStatusException(ConflictException):
    """
    결제 상태 때문에 할 수 없음
    - 결제대기가 아닌데 승인 / 결제완료가 아닌데 환불
    - 이미 처리된 결제가 있는데 다시 시작 (재시도 금지)
    - 예매가 결제할 수 있는 상태(예매대기)가 아님
    - 바뀔 HTTP 상태 : 409
    """
    def __init__(self, message: str = "유효하지 않은 결제 상태입니다.", error_code: str = "PAYMENT_STATUS_INVALID"):
        super().__init__(message, error_code=error_code)


# 3. 찾는 대상이 없음 (404)
class PaymentNotFoundException(NotFoundException):
    """
    예매에 연결된 결제가 없음
    - 바뀔 HTTP 상태 : 404
    """
    def __init__(self, message: str = "결제 정보를 찾을 수 없습니다."):
        super().__init__(message, error_code="PAYMENT_NOT_FOUND")


# 4. 외부 결제사(토스) 호출 실패 (400 / 502)
class PaymentGatewayException(SharedException[None]):
    """토스 호출 실패. 토스가 4xx로 거절하면 400, 연결 실패·5xx는 502."""

    def __init__(self, message: str, error_code: str = "TOSS_ERROR", status_code: int = status.HTTP_502_BAD_GATEWAY):
        super().__init__(message, status_code=status_code, error_code=error_code)
