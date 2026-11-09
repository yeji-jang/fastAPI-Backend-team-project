"""결제 저장 계약. DB 구현은 infrastructure가 맡는다."""

from abc import ABC, abstractmethod

from asyncticket.payment.domain.payment import Payment


class PaymentRepository(ABC):
    """상위 계층에는 SQLAlchemy 객체가 아닌 Payment를 준다."""

    @abstractmethod
    async def find_by_id(self, pay_id: int) -> Payment | None:
        """결제 한 건을 찾는다. 없으면 None을 반환한다."""
        raise NotImplementedError

    @abstractmethod
    async def find_by_reserv_id(self, reserv_id: int) -> Payment | None:
        """예약 ID로 결제 정보 조회"""

    @abstractmethod
    async def save(self, payment: Payment) -> None:
        """결제 상태를 저장한다. 새 결제면 받은 pay_id·created_at을 payment에 채운다.
        commit은 요청 세션(get_db)이 끝날 때 한다."""
        raise NotImplementedError
