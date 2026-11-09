"""
예매 도메인 예외 -> 팀 공통 응답 변환 (표현계층)
    - 도메인, 응용, 계층은 HTTP를 모르고 예매 도메인 예외만 던진다
    - 여기서 상태 코드를 붙여 팀 공통 처리기로 넘긴다
"""


from fastapi import (
    FastAPI,   # 앱 예외 처리기 등록
    Request,   # 예외 처리기가 받는 요청정보
    )
from fastapi.responses import JSONResponse

# <공통 예외>
from asyncticket.shared.core.exceptions import(
    ConflictException,
    ForbiddenException,
    NotFoundException,
    SharedException,
    ValidationException
)

# <domain - 예매 예외>
from asyncticket.reservations.domain.reservation import(
    ReservationError,
    ReservationForbiddenError,
    ReservationNotFoundError,
    ReservationValidationError
)


def to_shared_exception(error : ReservationError) -> SharedException :
    """
    예매 도메인 예외 -> 팀 공통 예외
    message, error_code는 그대로
    """

    # 403
    if isinstance(error, ReservationForbiddenError) :
        return ForbiddenException(error.message, error_code=error.error_code)

    # 404
    if isinstance(error, ReservationNotFoundError) :
        return NotFoundException(error.message, error_code=error.error_code)

    # 422
    if isinstance(error, ReservationValidationError) :
        return ValidationException(error.message, error_code=error.error_code)

    # 409
    return ConflictException(error.message, error_code=error.error_code)


def register_reservation_errors(app : FastAPI) -> None :
    """
    앱에 예매 도메인 예외 처리기 등록
    팀 공통 처리기를 먼저 등록한 뒤 호출
    """

    shared_handler = app.exception_handlers[SharedException]

    async def reservation_error(request : Request, exc : ReservationError) -> JSONResponse : 
        # 팀 공통 예외로 바꿔서 통역된 예외를 팀 공통 처리기에 넘겨서 응답을 만든다
        return await shared_handler(request, to_shared_exception(exc))

    app.add_exception_handler(ReservationError, reservation_error)
