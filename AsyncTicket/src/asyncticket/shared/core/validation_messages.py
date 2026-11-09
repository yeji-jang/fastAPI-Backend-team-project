"""Pydantic 오류 종류를 사용자에게 보여줄 한국어 안내로 변환한다."""
from typing import Any


def korean_validation_message(error: dict[str, Any]) -> str:
    kind = error.get("type", "")
    context = error.get("ctx") or {}
    messages = {
        "missing": "필수 입력값입니다.",
        "extra_forbidden": "허용되지 않은 입력 항목입니다.",
        "int_type": "정수를 입력해 주세요.",
        "int_parsing": "정수로 변환할 수 있는 값을 입력해 주세요.",
        "int_from_float": "소수점이 없는 정수를 입력해 주세요.",
        "string_type": "문자열을 입력해 주세요.",
        "list_type": "목록 형식으로 입력해 주세요.",
        "dict_type": "객체 형식으로 입력해 주세요.",
        "bool_type": "참 또는 거짓 값을 입력해 주세요.",
        "bool_parsing": "참 또는 거짓으로 해석할 수 있는 값을 입력해 주세요.",
        "float_type": "숫자를 입력해 주세요.",
        "float_parsing": "숫자로 변환할 수 있는 값을 입력해 주세요.",
        "finite_number": "유한한 숫자를 입력해 주세요.",
        "json_invalid": "요청 본문이 올바른 JSON 형식이 아닙니다.",
        "model_attributes_type": "요청 본문을 올바른 객체 형식으로 입력해 주세요.",
        "date_parsing": "올바른 날짜를 입력해 주세요.",
        "date_from_datetime_parsing": "올바른 날짜를 입력해 주세요.",
        "datetime_parsing": "올바른 날짜와 시각을 입력해 주세요.",
        "datetime_from_date_parsing": "올바른 날짜와 시각을 입력해 주세요.",
        "timezone_aware": "시각에 시간대를 포함해 주세요.",
    }
    if kind in messages:
        return messages[kind]
    limits = {
        "greater_than": ("gt", "초과하는 값을 입력해 주세요."),
        "greater_than_equal": ("ge", "이상의 값을 입력해 주세요."),
        "less_than": ("lt", "미만의 값을 입력해 주세요."),
        "less_than_equal": ("le", "이하의 값을 입력해 주세요."),
    }
    if kind in limits:
        key, message = limits[kind]
        return f"{context.get(key)} {message}"
    if kind == "string_too_short":
        return f"최소 {context.get('min_length')}자 이상 입력해 주세요."
    if kind == "string_too_long":
        return f"최대 {context.get('max_length')}자까지 입력할 수 있습니다."
    if kind == "too_short":
        return f"최소 {context.get('min_length')}개 이상의 항목이 필요합니다."
    if kind == "too_long":
        return f"최대 {context.get('max_length')}개의 항목을 입력할 수 있습니다."
    # 미등록 오류도 영어 원문이나 입력값을 노출하지 않고 한국어 안내로 반환한다.
    return "입력값의 형식 또는 허용 범위를 확인해 주세요."
