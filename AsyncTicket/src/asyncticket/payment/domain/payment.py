"""
1. 결제는 예매 접수시에 함께 생성이 된다.
2. 예매 접수시에는 결제를 위한 기본 정보만 추가(예약 ID - reserv_id, 예약 금액 - amount, 결제 상태는 READY)
3. 예매 접수 -> 결제 창 -> 결제 완료 -> 백앤드로 (paymentKey,amount,orderID) 데이터가 URL을 통해서 넘어온다.
4. 넘어온 paymentKey, amount, orderId를 통해서 결제 승인 처리를 백앤드에서 진행하면 실 결제가 이뤄지게 된다.
5. 결제가 성공한다면 결제 상태는 DONE이 되고, 예매는 확정이 된다.
6. 실패한다면 예매는 취소 처리된다.
7. 결제 취소는 paymentKey를 가지고 진행이 되며, 결제 취소가 되면 예매도 취소가 된다.
8. amount가 변조가 되어 있으면 결제되었더라도 취소 처리를 한다.
"""

from datetime import datetime
from typing import Dict, List
from decimal import Decimal
from dataclasses import dataclass
from payment.domain.enums import PaymentStatus
from payment.domain.service import PaymentProcess
from payment.domain.exceptions import PaymentAmountInvalidException, PaymentStatusException, PaymentException
from shared.core.logger import get_logger

logger = get_logger(__file__)


@dataclass(frozen=True)
class PaymentLog:
    value: Dict[str, str]


@dataclass
class Payment:
    pay_id: int
    reserv_id: int
    amount: Decimal

    created_at: datetime | None = None
    paid_at: datetime | None = None
    refunded_at: datetime | None = None
    
    payment_key: str | None = None
    method: str | None = None
    status: PaymentStatus = PaymentStatus.READY

    logs: List[PaymentLog] = []



    @classmethod # 정적
    def create(cls, reserv_id: int, amount: Decimal):
        """결제 등록"""
        return cls(
            reserv_id,
            amount
        )

    async def approve(self, payment_key: str, reserv_id: int, amount: int, processor: PaymentProcess):
        """결제 승인 처리"""
        # 결제 전 상태에서만 진행 가능
        if self.status != PaymentStatus.READY:
            raise PaymentStatusException("입금 전 상태만 결제가 가능합니다.")


        # 결제 금액 변조 경우는 처리를 하지 않는다.
        if self.amount != amount:
            raise PaymentAmountInvalidException
        try:
            payment_log = await processor.approve(payment_key, reserv_id, amount)
        
            # 결제 승인 성공 시에는 로그를 기록하고 결제 상태를 PAID으로 변경한다.
            self.logging(payment_log)
            self.status = PaymentStatus.PAID
        except Exception as e:
            # 결제 실패
            logger.error(f"[결제 실패] 예약 ID:{reserv_id}, 예약 금액: {amount}, 실패 사유: {str(e)}")
            raise PaymentException(f"결제를 실패했습니다. 예약 ID: {self.reserv_id}")
        

    async def cancel(self, reason: str, processor: PaymentProcess):
        """결제 취소"""
        # 결제가 된 상태에서만 취소가 가능 
        if self.status != PaymentStatus.PAID:
            raise PaymentStatusException("결제 취소는 입금 확인 상태에서만 가능합니다.")

        # payment key와 reason은 필수
        if not self.payment_key:
            raise PaymentException("payment_key는 취소 시 필수입니다.")

        if not self.reason or self.reason.strip()
            raise PaymentException("취소 사유는 필수입니다.")

        try:
            paymeny_log = await processor.cancel(self.payment_key, self.reserv_id, reason)
            self.logging(paymeny_log)
            self.status = PaymentStatus.REFUNDED

        except Exception as e:    
            logger.error(f"[결제 취소 실패] 예약 ID:{self.reserv_id}, 예약 금액: {self.amount}, 취소 사유: {str(e)}")
            raise PaymentException(f"결제 취소에 실패했습니다. 예약 ID: {self.reserv_id}")
        self.logging(paymeny_log)


    def logging(self, log: List[Dict[str,str]]):
        """결제/취소 로그"""
        self.logs.append(log)

