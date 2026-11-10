"""
<결제 상태>
- 결제 엔티티(payment.py)가 상태를 바꾸고, DB(payments.status)에는 오른쪽 값이 저장된다
- 상태 이름은 토스 상태에 맞추지 않고 팀이 정한 값을 유지한다 (2026-11-06 결정)

<도메인 비즈니스 요구사항 정의>
    1) 결제는 4가지 상태로 관리
        - 결제대기(READY)            : 예매대기 생성 후 결제 시작, 토스 승인 전
        - 결제완료(PAID  → "DONE")   : 토스 승인 성공
        - 결제실패(FAILED → "FAIL")  : 토스 승인 거절, 또는 새 결제 시도로 대체됨
            · 2026-11-09 이후 : 승인 실패는 요청 전체가 rollback되어 READY로 남는다.
              같은 예매로 새 결제를 만들지 않으므로(재시도 금지) 이 값은 지금 코드에서 저장되지 않는다.
        - 환불완료(REFUNDED → "REFUND") : 결제완료 후 토스 취소 성공 (예매 취소가 내부 호출)
"""

from enum import StrEnum

# 1. 결제 상태 (요구사항 1번)
class PaymentStatus(StrEnum):
    READY = "READY"       # 결제대기 (토스 승인 전)
    PAID = "DONE"         # 결제완료 (토스 승인 성공)
    FAILED = "FAIL"       # 결제실패 (승인 거절, 새 시도로 대체)
    REFUNDED = "REFUND"   # 환불완료 (토스 취소 성공)
