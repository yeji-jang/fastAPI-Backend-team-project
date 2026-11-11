"""
결제 → 예매 연결 어댑터 (ReservationGateway 구현)
    - 예매 담당 코드는 수정하지 않고, 공개된 예매 서비스 메서드만 호출한다.
        get_reservation(reserv_id, ticketholder_id) : 본인 확인 포함 단건 조회
        confirm(reserv_id, pay_id)                  : 결제 후 예매 확정
    - 예매 상태 값(PENDING)은 여기서만 안다. 예매 상태가 바뀌면 이 파일만 고친다.
    - 예매 쪽 예외(없음 404, 본인 아님 403, 확정 불가 409)는 바꾸지 않고 그대로 올려 보낸다
    - 예매 쪽 같은 구조 : reservations/infrastructure/adapter_seat_allocation.py (좌석 서비스를 감쌈)
"""

# <Application - 결제>
from asyncticket.payment.application.ports import ReservationForPayment, ReservationGateway # 결제가 정한 약속

# <예매 도메인 - 호출만 한다>
from asyncticket.reservations.application.service import ReservationService # 예매 응용 서비스
from asyncticket.reservations.domain.enums import ReservationStatus # 예매 상태 (PENDING 판단용)


# 1. 예매 연결 어댑터
class ReservationGatewayAdapter(ReservationGateway):
    def __init__(self, service: ReservationService):
        self._service = service     # wiring/payment.py가 같은 요청 세션으로 만든 예매 서비스

    # 1) 본인 예매 조회 → 결제에 필요한 값만 꺼낸다
    async def get_for_payment(self, *, reserv_id: int, ticketholder_id: int) -> ReservationForPayment:
        reservation = await self._service.get_reservation(reserv_id=reserv_id, ticketholder_id=ticketholder_id)
        return ReservationForPayment(
            reserv_id=reserv_id,
            amount=reservation.total_amount,
            payable=reservation.status == ReservationStatus.PENDING,
        )

    # 2) 결제 성공 후 예매 확정 (예매대기 → 예매확정)
    async def confirm(self, *, reserv_id: int, pay_id: int) -> None:
        await self._service.confirm(reserv_id=reserv_id, pay_id=pay_id)
