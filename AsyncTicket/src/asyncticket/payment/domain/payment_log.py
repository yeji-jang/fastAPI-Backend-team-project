"""
<결제 기록 (VO)>
- 토스가 돌려준 승인·취소 응답 1건을 그대로 담는 값 객체
- 다른 결제 모듈을 import하지 않는다
    → payment.py(엔티티)와 service.py(토스 포트)가 둘 다 이 파일을 가져다 써도 순환 import가 생기지 않는다
    → 예전에 PaymentLog가 payment.py 안에 있을 때 payment.py ↔ service.py 순환 import가 났다 (2026-11-09 분리)
- 저장 : infrastructure/repositories.py가 payments.payment_log(JSONB)의 "logs" 목록으로 저장한다
"""

from dataclasses import dataclass
from typing import Any


# 1. VO(Value Object)
@dataclass(frozen=True)
class PaymentLog:
    """토스 응답 1건 (승인 또는 취소)"""
    # 토스 응답 JSON 그대로 (승인·취소 1건당 1개)
    value: dict[str, Any]
