"""
결제 응용 계층이 예매 도메인에 요청하는 기능 (포트)
    - 결제는 예매 코드를 직접 알지 않고 이 약속만 사용한다.
    - 실제 구현은 payment/infrastructure/adapter_reservation.py가 예매 서비스를 호출해 채운다.
    - 예매 담당의 SeatAllocation 포트와 같은 방식이다.
    - 결제가 예매에게 원하는 것은 세 가지뿐이다
        1) 이 예매의 금액은 얼마인가
        2) 지금 결제할 수 있는 상태(예매대기)인가 — 본인 예매인지는 예매가 판단
        3) 결제가 성공했으니 예매를 확정해 달라
    - 예매 상태 값(PENDING 등)은 이 파일에 없다 → 예매 상태가 바뀌어도 결제 서비스는 그대로
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal # 예매 금액


# 1. 결제에 필요한 예매 정보 (VO)
@dataclass(frozen=True)
class ReservationForPayment:
    """결제가 보는 예매 (예매 엔티티 전체가 아니라 필요한 값만)"""
    reserv_id: int
    amount: Decimal      # 예매 총액 (결제 금액의 기준)
    payable: bool        # 결제할 수 있는 상태(예매대기)인지


# 2. 예매에 요청하는 기능 (포트)
class ReservationGateway(ABC):
    # 1) 본인 예매 조회 (금액·결제 가능 여부)
    @abstractmethod
    async def get_for_payment(self, *, reserv_id: int, ticketholder_id: int) -> ReservationForPayment:
        """본인 예매를 조회한다. 없거나 본인 것이 아니면 예매 쪽 예외가 그대로 올라간다."""

    # 2) 결제 성공 후 예매 확정
    @abstractmethod
    async def confirm(self, *, reserv_id: int, pay_id: int) -> None:
        """결제 성공을 예매에 알려 확정한다. 확정할 수 없으면(만료 등) 예매 쪽 예외가 올라간다."""
