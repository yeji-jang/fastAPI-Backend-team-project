"""표현 계층 공통 입력 규칙: JSON 형식과 명세의 자료형을 검증한다."""

import re
from datetime import date
from typing import Annotated, Self

from pydantic import AwareDatetime, BaseModel, BeforeValidator, ConfigDict, Field, model_validator


def require_date_text(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("날짜는 YYYY-MM-DD 형식이어야 합니다.")
    return value


def require_datetime_text(value: object) -> str:
    if not isinstance(value, str) or not re.match(r"^\d{4}-\d{2}-\d{2}T", value):
        raise ValueError("시각은 시간대를 포함한 ISO 8601 문자열이어야 합니다.")
    return value


IsoDate = Annotated[date, BeforeValidator(require_date_text)]
IsoDatetime = Annotated[AwareDatetime, BeforeValidator(require_datetime_text)]


class PatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", title="부분 수정 요청")

    @model_validator(mode="after")
    def validate_patch(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("변경할 필드를 하나 이상 보내 주세요.")
        nullable = {"description", "performer", "runtime"}
        for name in self.model_fields_set - nullable:
            if getattr(self, name) is None:
                raise ValueError(f"{name}에는 null을 지정할 수 없습니다.")
        return self


class ErrorDetail(BaseModel):
    model_config = ConfigDict(title="오류 상세 정보")
    code: str = Field(title="오류 코드", description="오류를 구분하는 코드")
    message: str = Field(title="오류 안내", description="사용자에게 표시할 오류 메시지")


class ErrorResponse(BaseModel):
    model_config = ConfigDict(title="오류 응답")
    detail: ErrorDetail = Field(title="상세 오류", description="오류 코드와 안내 메시지")
