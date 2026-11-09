"""
요구사항 정의

1. 결제는 4가지 상태로 관리
    - 결제대기(READY)    : 예매대기 생성 직후, 토스 승인 전
    - 결제완료(PAID)     : 토스 승인 성공
    - 결제실패(FAILED)   : 토스 승인 거절, 또는 새 결제 시도로 대체됨
    - 환불완료(REFUNDED) : 결제완료 후 토스 취소 성공
"""

from enum import StrEnum

# 비즈니스 요구사항 1 - 결제상태 관리
class PaymentStatus(StrEnum):
    READY = "READY"       # 결제대기 (토스 승인 전)
    PAID = "DONE"         # 결제완료 (토스 승인 성공)
    FAILED = "FAIL"       # 결제실패 (승인 거절, 새 시도로 대체)
    REFUNDED = "REFUND"   # 환불완료 (토스 취소 성공)
