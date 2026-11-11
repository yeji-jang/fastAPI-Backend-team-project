"""
결제 응용 서비스 (순서 조율)
    1.
        - 규칙 판단은 결제 엔티티(domain/payment.py)가 하고, 응용 계층에서는 순서대로 호출만 한다
        - 예매는 포트(ReservationGateway)로만 부르고, 토스는 포트(PaymentProcess)로만 부른다

트랜잭션 원칙
    - commit은 하지 않는다. 요청이 끝날 때 get_db가 commit, 예외가 나면 전체 rollback.
    - 토스 호출(외부)은 DB 변경 뒤 맨 마지막에 둔다.
      토스가 실패하면 예외가 올라가 DB 변경이 모두 rollback된다.
    - DB rollback은 토스에 이미 처리된 승인·환불을 되돌리지 못한다.
      "토스 성공 후 commit 실패"는 남는 틈이라 로그를 남긴다(대조 필요).

    2. 결제 시작(순서) :
        1) 본인 예매 조회 (금액, 결제 가능 여부)
        2) 결제 가능 상태 확인
        3) 기존 결제 확인 (READY면 그대로 반환, 처리된 결제면 거절)
        4) 결제대기(READY) 생성·저장
    3. 결제 승인(순서) :
        1) 주문번호에서 reserv_id 꺼내기
        2) 본인 예매 확인
        3) 결제 조회 + 승인 규칙 확인 → 결제완료 저장
        4) 예매 확정
        5) 토스 승인 (마지막 외부 호출)
        6) 토스 응답 기록·저장
    4. 환불(순서) : 예매 취소가 내부 호출
        1) 결제 조회 + 환불 규칙 확인 → 환불완료 저장
        2) 토스 취소 (마지막 외부 호출)
        3) 토스 응답 기록·저장
    5. 조회 : 본인 예매의 결제
"""

from datetime import datetime, timezone
from decimal import Decimal # 결제 금액

# <Application - 결제>
from asyncticket.payment.application.ports import ReservationGateway # (추상)예매 연결

# <Domain - 결제>
from asyncticket.payment.domain.enums import PaymentStatus # 결제 상태
from asyncticket.payment.domain.exceptions import (
    PaymentNotFoundException,   # 404
    PaymentStatusException,     # 409
)
from asyncticket.payment.domain.order_id import make_order_id, parse_order_id # 토스 주문번호 규칙
from asyncticket.payment.domain.payment import Payment # 결제 엔티티
from asyncticket.payment.domain.repository import PaymentRepository # (추상)결제 저장소
from asyncticket.payment.domain.service import PaymentProcess # (추상)토스 호출

# <Shared>
from asyncticket.shared.core.logger import get_logger

logger = get_logger(__name__)


class PaymentService:

    # 0. 부품 받기 (wiring/payment.py가 요청 세션 하나로 만들어 꽂는다)
    def __init__(
        self,
        *,
        payment_repo: PaymentRepository,
        processor: PaymentProcess,
        reservations: ReservationGateway,
        order_prefix: str,
    ):
        self.payment_repo = payment_repo    # 결제 저장소
        self.processor = processor          # 토스 호출
        self.reservations = reservations    # 예매 연결
        self.order_prefix = order_prefix    # 주문번호 접두어 (TOSS_ORDER_PREFIX)

    # 결제의 토스 주문번호 (응답에 담아 프론트가 결제창에 그대로 쓴다)
    def order_id_of(self, payment: Payment) -> str:
        return make_order_id(self.order_prefix, payment.reserv_id)

    # 1. 결제 시작 : 본인 예매대기 확인 → READY 생성 (이미 READY면 그대로 반환)
    async def start(self, *, reserv_id: int, ticketholder_id: int) -> tuple[Payment, bool]:
        """반환: (결제, 새로 만들었는지)"""
        # 1) 본인 예매 조회 (없거나 남의 예매면 예매 쪽 예외)
        reservation = await self.reservations.get_for_payment(
            reserv_id=reserv_id, ticketholder_id=ticketholder_id,
        )
        # 2) 예매대기가 아니면 결제할 수 없다
        if not reservation.payable:
            raise PaymentStatusException("결제할 수 있는 예매 상태가 아닙니다.", error_code="RESERVATION_NOT_PAYABLE")

        # 3) 기존 결제 확인
        existing = await self.payment_repo.find_by_reserv_id(reserv_id)
        if existing is not None:
            # 같은 orderId로 결제창을 다시 여는 것은 허용(토스는 미승인 orderId 재사용 가능)
            if existing.status == PaymentStatus.READY:
                return existing, False
            # 재시도 금지: 승인·실패·환불된 결제가 있으면 새로 시작하지 않는다
            raise PaymentStatusException("이미 처리된 결제가 있어 다시 결제할 수 없습니다.", error_code="PAYMENT_ALREADY_PROCESSED")

        # 4) 결제대기 생성 (금액은 예매 금액) → 저장
        payment = Payment.create(reserv_id, reservation.amount)
        await self.payment_repo.save(payment)
        return payment, True

    # 2. 결제 승인 : 검증 → 결제 DONE 저장 → 예매 확정 → 토스 승인(마지막) → 응답 기록
    async def approve(
        self, *, payment_key: str, order_id: str, amount: Decimal, ticketholder_id: int,
    ) -> Payment:
        now = datetime.now(timezone.utc)
        # 0) 주문번호에서 reserv_id 꺼내기 (형식이 틀리면 400)
        reserv_id = parse_order_id(self.order_prefix, order_id)

        # 1) 본인 예매인지 (없거나 남의 예매면 예매 쪽 예외)
        await self.reservations.get_for_payment(reserv_id=reserv_id, ticketholder_id=ticketholder_id)

        # 2) 결제 조회 + 상태·금액 규칙 (어기면 토스를 호출하지 않는다)
        payment = await self._get(reserv_id)
        payment.mark_paid(payment_key=payment_key, amount=amount, now=now)
        await self.payment_repo.save(payment)

        # 3) 예매 확정 (만료 등으로 실패하면 토스 호출 전에 끝나 결제되지 않는다)
        assert payment.pay_id is not None
        await self.reservations.confirm(reserv_id=reserv_id, pay_id=payment.pay_id)

        # 4) 토스 승인 (외부 호출은 마지막. 실패하면 예외 → 1~3 rollback)
        log = await self.processor.approve(payment_key=payment_key, order_id=order_id, amount=payment.amount)

        # 5) 응답 기록. 여기 이후 commit이 실패하면 토스만 승인된 상태가 된다 → 로그로 추적
        logger.info(f"[결제 승인] order_id={order_id} pay_id={payment.pay_id} amount={payment.amount}")
        payment.record(log)
        await self.payment_repo.save(payment)
        return payment

    # 3. 환불 : 예매 취소가 내부에서 호출 (공개 API 없음, 본인 확인은 예매가 끝낸 상태)
    async def refund_for_reservation(self, *, reserv_id: int, reason: str) -> Payment:
        """예매 취소의 마지막 단계에서 같은 요청 세션으로 호출해야 한 트랜잭션으로 묶인다."""
        now = datetime.now(timezone.utc)

        # 1) 결제 조회 + 환불 규칙
        payment = await self._get(reserv_id)
        payment.mark_refunded(reason=reason, now=now)
        await self.payment_repo.save(payment)

        # 2) 토스 취소 (외부 호출은 마지막. 실패하면 예외 → 예매 취소까지 rollback)
        assert payment.payment_key is not None
        log = await self.processor.cancel(payment_key=payment.payment_key, reason=reason)

        # 3) 응답 기록
        logger.info(f"[결제 환불] reserv_id={reserv_id} pay_id={payment.pay_id} amount={payment.amount}")
        payment.record(log)
        await self.payment_repo.save(payment)
        return payment

    # 4. 조회 : 본인 예매의 결제
    async def get_for_reservation(self, *, reserv_id: int, ticketholder_id: int) -> Payment:
        # 1) 본인 예매인지 → 2) 결제 조회
        await self.reservations.get_for_payment(reserv_id=reserv_id, ticketholder_id=ticketholder_id)
        return await self._get(reserv_id)

    # 5. 공통 : 예매의 결제 조회 (없으면 404)
    async def _get(self, reserv_id: int) -> Payment:
        payment = await self.payment_repo.find_by_reserv_id(reserv_id)
        if payment is None:
            raise PaymentNotFoundException()
        return payment
