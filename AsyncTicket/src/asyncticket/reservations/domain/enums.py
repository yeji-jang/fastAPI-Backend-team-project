"""
요구사항 정의

1. 예매는 4가지 상태로 관리
    - 예매대기(PENDING)   : 예매 생성 직후, 결제 전
    - 예매확정(CONFIRMED) : 결제 성공 후
    - 예매취소(CANCELED)  : 확정된 예매를 취소
    - 예매만료(EXPIRED)   : 결제하지 않고 결제 대기 시간이 지난 예매
"""

from enum import StrEnum

# 비즈니스 요구사항 1 - 예매상태 관리
class ReservationStatus(StrEnum):
    PENDING = "PENDING"     # 예매대기 (결제 전)
    CONFIRMED = "CONFIRMED" # 예매확정 (결제 성공)
    CANCELED = "CANCELED"   # 예매취소
    EXPIRED  = "EXPIRED"    # 예매만료 (결제 시간 초과) - 토스페이 유효기간을 쓰지않아 예매 자체에서 관리