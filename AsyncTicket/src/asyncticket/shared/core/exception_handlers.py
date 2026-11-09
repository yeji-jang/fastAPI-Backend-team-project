from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from asyncticket.shared.core.exceptions import SharedException
from asyncticket.shared.core.logger import get_logger
from asyncticket.shared.core.schemas import APIResponse
from asyncticket.shared.core.validation_messages import korean_validation_message

logger = get_logger(__name__)

def register_exception_handlers(app: FastAPI) -> None:
    # 비즈니스 예외 (SharedException 및 도메인 하위 예외)
    @app.exception_handler(SharedException)
    async def shared_exception_handler(request: Request, exc: SharedException):
        if exc.status_code >= 500:
            logger.error("비즈니스 서버 오류 [%s]: %s", exc.error_code, exc.message)
        else:
            logger.warning(
                "클라이언트 요청 예외 [%s]: %s (path: %s, method: %s)",
                exc.error_code,
                exc.message,
                request.url.path,
                request.method
            )

        response_dto = APIResponse.fail(
            code=exc.error_code,
            message=exc.message,
            errors=exc.errors
        )

        return JSONResponse(
            status_code=exc.status_code,
            content=response_dto.model_dump(mode='json')
        )

    # Pydantic 스키마 검증 실패 (422)
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors_map: dict[str, list[str]] = {}
        for err in exc.errors():
            loc = ".".join(str(item) for item in err["loc"] if item != "body")
            field_name = loc if loc else "non_field_errors"
            errors_map.setdefault(field_name, []).append(korean_validation_message(err))

        logger.warning("요청 파라미터 유효성 검증 실패 (path: %s, method: %s): %s", request.url.path, request.method, errors_map)

        response_dto = APIResponse.fail(
            code="REQUEST_VALIDATION_ERROR",
            message="요청 입력값 검증에 실패했습니다.",
            errors=errors_map,
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=response_dto.model_dump(mode="json"),
        )

    # 처리되지 않은 시스템 내부 오류 (500)
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("처리되지 않은 치명적 시스템 오류 발생 (path: %s, method: %s): %s", request.url.path, request.method, exc)

        response_dto = APIResponse.fail(
            code="INTERNAL_SERVER_ERROR",
            message="서버 내부 오류가 발생했습니다. 관리자에게 문의해주세요.",
            errors=None,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_dto.model_dump(mode="json"),
        )
