from shared.core.exceptions import BadRequestException, NotFoundException

class PaymentException(BadRequestException):
    def __init__(self, message: str):
        super().__init__(message)


    
class PaymentAmountInvalidException(PaymentException):
    def __int__(self):
        super().__init__("결제 금액이 유효하지 않습니다.")


class PaymentStatusException(PaymentException):
    def __init__(self, message: str = "유효하지 않은 결제 상태입니다."):
        super().__init__(message)

class PaymentNotFoundException(NotFoundException):
    def __init__(self, message: str = "결제 정보를 찾을 수 없습니다."):
        super().__init__(message)