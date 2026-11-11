"""공연·회차의 순수 도메인 예외를 팀 공통 예외 처리기에 연결한다."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from asyncticket.shared.core.exceptions import (
    ConflictException, ForbiddenException, NotFoundException, SharedException,
    UnauthorizedException, ValidationException,
)
from asyncticket.shared.domain.catalog import (
    AuthenticationRequiredError, CatalogConflictError, CatalogForbiddenError,
    CatalogIntegrationError, CatalogNotFoundError, CatalogValidationError,
)


def to_shared_exception(exc: Exception) -> SharedException:
    # HTTP 상태를 가진 공통 예외는 표현 계층에서 만든다. 서비스·도메인은
    # FastAPI를 참조하지 않으며 기존 코드·메시지와 트랜잭션 경계를 유지한다.
    if isinstance(exc, AuthenticationRequiredError):
        return UnauthorizedException(str(exc), error_code="AUTHENTICATION_REQUIRED")
    if isinstance(exc, CatalogForbiddenError):
        return ForbiddenException(str(exc), error_code="PERMISSION_DENIED")
    if isinstance(exc, CatalogNotFoundError):
        return NotFoundException(str(exc), error_code="RESOURCE_NOT_FOUND")
    if isinstance(exc, CatalogConflictError):
        return ConflictException(str(exc), error_code="RESOURCE_CONFLICT")
    if isinstance(exc, CatalogValidationError):
        return ValidationException(str(exc), error_code="VALIDATION_ERROR")
    if isinstance(exc, CatalogIntegrationError):
        return SharedException(str(exc), status_code=503, error_code="INTEGRATION_UNAVAILABLE")
    raise TypeError("공연·회차 HTTP 변환에 등록되지 않은 예외입니다.")


def register_catalog_errors(app: FastAPI) -> None:
    # main에서 팀 공통 처리기를 먼저 등록한다. 요청 검증/미처리 오류는
    # 공통 처리기만 담당하며 이 어댑터에서 중복 등록하지 않는다.
    shared_handler = app.exception_handlers[SharedException]

    async def domain_error(request: Request, exc: Exception) -> JSONResponse:
        common_error = to_shared_exception(exc)
        response = await shared_handler(request, common_error)
        # 팀 공통 401 예외에는 헤더 기능이 없어 기존 Bearer 계약을 여기서 보존한다.
        if common_error.status_code == 401:
            response.headers["WWW-Authenticate"] = "Bearer"
        return response

    for error in (
        AuthenticationRequiredError, CatalogForbiddenError, CatalogNotFoundError,
        CatalogConflictError, CatalogValidationError, CatalogIntegrationError,
    ):
        app.add_exception_handler(error, domain_error)
