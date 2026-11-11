# 팀원 사용 방법
# 기준: 사용자가 확인한 팀 API 명세의 반복 오류 항목. 아래 업무 코드는 사용 예시입니다.
# 미확정 권한·상태 규칙을 이 파일에서 확정하거나 자동 검사하지 않습니다.
# 1. 이 파일에 공연·좌석·예매 필드를 추가하지 않고, 자기 서비스에서 필요한 예외를 import합니다.
#    from asyncticket.shared.core.exceptions import NotFoundException
# 2. 자기 업무의 실패 조건을 확인한 자리에서 raise합니다.
#    if seat is None:
#        raise NotFoundException("좌석을 찾을 수 없습니다.", error_code="SEAT_NOT_FOUND")
# 3. message에는 사용자에게 보여줄 문장, error_code에는 오류를 구분할 업무 코드를 넣습니다.
#    비밀번호·토큰·SQL·DB 접속 정보는 메시지에 넣지 않습니다.
# 4. 공통 처리기가 등록된 앱에서는 예외를 실패 JSON으로 바꿉니다.
#    라우터에서 예외를 잡아 None을 반환하면 성공 응답으로 보일 수 있으므로 그대로 전달합니다.
# 5. 기존 전용 예외를 사용하는 담당자는 자기 코드의 import·raise와 테스트를 공통 예외에 맞춥니다.
#    공통 예외를 상속한 세부 예외도 사용할 수 있습니다. 기존 전용 예외의 자동 변환은 없습니다.
# 예외 발생만으로 DB 저장·롤백이 완료되지는 않습니다. 트랜잭션 처리는 유스케이스에서 유지합니다.

from typing import Generic, TypeVar
from fastapi import status

T = TypeVar("T")


# 공통 부모입니다. 보통 아래의 구체적인 예외를 골라 사용합니다.
class SharedException(Exception, Generic[T]):
    """모든 애플리케이션 예외의 공통 부모 클래스"""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        error_code: str = "BAD_REQUEST",
        errors: T | None = None,
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.errors: T | None = errors
        super().__init__(message)


# 400: 튜터 기본 틀로 유지합니다. 확인한 팀 명세에는 아직 사용처가 없습니다.
# 명세상 422인 입력 오류를 임의로 400으로 바꾸지 않습니다.
# 사용할 경우 message는 필수이며, errors에 상세 내용을 넣을 수 있습니다.
class BadRequestException(SharedException[T]):
    def __init__(
        self,
        message: str,
        error_code: str = "BAD_REQUEST",
        errors: T | None = None,
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code=error_code,
            errors=errors,
        )


# 401: 인증 정보가 없거나 무효인 경우. 실제 토큰 검사는 인증 담당 코드가 수행합니다.
# 예: raise UnauthorizedException("로그인이 필요합니다.", error_code="AUTHENTICATION_REQUIRED")
class UnauthorizedException(SharedException[None]):
    def __init__(
        self,
        message: str = "인증되지 않은 사용자입니다.",
        error_code: str = "UNAUTHORIZED",
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code=error_code,
            errors=None,
        )


# 403: 인증은 됐지만 해당 작업 권한이 없는 경우입니다.
# SELLER/ADMIN 허용 범위와 소유권 규칙은 팀 정책을 따르며 여기서 정하지 않습니다.
# 예: raise ForbiddenException("수정 권한이 없습니다.", error_code="PERMISSION_DENIED")
class ForbiddenException(SharedException[None]):
    def __init__(
        self,
        message: str = "리소스에 접근할 권한이 없습니다.",
        error_code: str = "FORBIDDEN",
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            error_code=error_code,
            errors=None,
        )


# 404: 요청 대상 자체 또는 요청에 필요한 참조 대상이 없을 때 같은 예외를 사용합니다.
# 실제 조회·존재 확인은 각 도메인의 서비스/저장소에서 수행합니다.
# 대상 없음 예: raise NotFoundException("공연을 찾을 수 없습니다.", error_code="SHOW_NOT_FOUND")
# 참조 없음 예: raise NotFoundException("참조할 공연장이 없습니다.", error_code="VENUE_NOT_FOUND")
# 회차 예: raise NotFoundException("회차를 찾을 수 없습니다.", error_code="PERFORMANCE_NOT_FOUND")
# 목록의 빈 배열이 정상인 API는 빈 결과를 404로 바꾸지 않습니다.
class NotFoundException(SharedException[None]):
    def __init__(
        self,
        message: str = "리소스를 찾을 수 없습니다.",
        error_code: str = "NOT_FOUND",
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code=error_code,
            errors=None,
        )


# 409: 중복 생성 또는 연결 데이터·현재 상태와 요청이 충돌할 때 사용합니다.
# 명세의 회차번호 중복, 연결 회차/예매가 있는 삭제 제한 등이 후보이며,
# 제안으로 남은 조건은 각 담당자가 확정한 뒤 적용합니다.
# 예: raise ConflictException("회차 번호가 중복됩니다.", error_code="ROUND_ALREADY_EXISTS")
# 예: raise ConflictException("연결된 회차가 있어 삭제할 수 없습니다.", error_code="SHOW_HAS_PERFORMANCES")
class ConflictException(SharedException[None]):
    def __init__(
        self,
        message: str = "리소스가 이미 존재합니다.",
        error_code: str = "CONFLICT",
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            error_code=error_code,
            errors=None,
        )


# 422: 팀 명세의 입력 형식·범위·시간 순서·허용 필드 등 검증 실패에 사용합니다.
# 요청 형식/자료형 검사는 Pydantic이 하고 RequestValidationError 처리기가 응답합니다.
# 서비스에서 기존 값과 비교해야 하는 시간 순서 등 업무 검증은 이 예외로 발생시킵니다.
# 상태값은 잘못된 값인지(422), 현재 상태와 충돌인지(409)를 각 API 명세로 구분합니다.
# field_errors는 {필드명: [안내 문장, ...]} 형태입니다.
# 예: raise ValidationException(field_errors={"booking_closes_at": ["공연 시작 이후일 수 없습니다."]})
# 500: 예상하지 못한 오류는 exception_handlers.py가 처리하므로 별도 클래스를 만들지 않습니다.
class ValidationException(SharedException[dict[str, list[str]]]):
    def __init__(
        self,
        message: str = "유효성 검사에 실패했습니다.",
        error_code: str = "VALIDATION_ERROR",
        field_errors: dict[str, list[str]] | None = None,
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code=error_code,
            errors=field_errors or {},
        )
# pyright: ignore[reportReturnType]
