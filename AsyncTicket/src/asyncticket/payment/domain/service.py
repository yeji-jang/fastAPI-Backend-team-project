from abc import ABC, abstractmethod
from payment.domain.payment import PaymentLog

class PaymentProcess(ABC):
    @abstractmethod
    async def approve(self, payment_key: str, reserv_id: int, amount: int) -> PaymentLog:
        pass

    @abstractmethod
    async def cancel(self, payment_key: str, reserv_id: int , reason: str) -> PaymentLog:
        pass