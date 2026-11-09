"""
결제 저장 계약. DB 구현은 infrastructure가 맡는다.
    - 실제 구현 : infrastructure/repositories.py (SqlAlchemyPaymentRepository)
        1) 결제 ID로 찾고
        2) 예매 ID로 찾고 (예매 1건 = 결제 1건)
        3) 새 결제를 저장하거나 바뀐 상태를 저장
    - commit은 하지 않는다 : 요청이 끝날 때 get_db가 commit (중간에 실패하면 전체 rollback)
"""

from abc import ABC, abstractmethod

# <Domain - 결제>
from asyncticket.payment.domain.payment import Payment # 결제 엔티티


# 1. 결제 저장소 약속
class PaymentRepository(ABC):
    """상위 계층에는 SQLAlchemy 객체가 아닌 Payment를 준다."""

    # 1) 결제 ID로 조회
    @abstractmethod
    async def find_by_id(self, pay_id: int) -> Payment | None:
        """결제 한 건을 찾는다. 없으면 None을 반환한다."""
        raise NotImplementedError

    # 2) 예매 ID로 조회
    @abstractmethod
    async def find_by_reserv_id(self, reserv_id: int) -> Payment | None:
        """예약 ID로 결제 정보 조회"""

    # 3) 저장 (새 결제는 INSERT, 기존 결제는 상태 변경)
    @abstractmethod
    async def save(self, payment: Payment) -> None:
        """결제 상태를 저장한다. 새 결제면 받은 pay_id·created_at을 payment에 채운다.
        commit은 요청 세션(get_db)이 끝날 때 한다."""
        raise NotImplementedError
