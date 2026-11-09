"""
DB 없이 예매 도메인의 생성, 검증, 취소 규칙을 확인

<테스트 읽는 법>
- 모든 테스트는 3단계로 되어 있다
    1) 준비 : 테스트에 필요한 예매를 만든다
    2) 실행 : 확인하고 싶은 동작(생성, 취소 등)을 한다
    3) 확인 : 결과가 기대한 값과 같은지 assert로 비교한다
- assert가 하나라도 틀리면 그 테스트는 실패(FAIL)한다
- assertRaises는 "이 예외가 발생해야 통과"라는 뜻이다

<실행 방법> (AsyncTicket 폴더에서)
    uv run python -m unittest tests.test_reservation_domain -v
"""

from dataclasses import FrozenInstanceError
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from asyncticket.reservations.domain.enums import ReservationStatus
from asyncticket.reservations.domain.reservation import (
    # 엔티티
    Reservation,
    # VO
    TicketHolder,
    ReservedPerformance,
    ReservedSeat,
    ReservedPayment,
    # 예외
    ReservationConflictError,
    ReservationForbiddenError,
    ReservationValidationError,
    # 상수
    PENDING_EXPIRE_MINUTES,
)


# 테스트에서 쓸 고정 시각과 아이디
#   예매 기간 : 11/1 ~ 11/30 (11/30 00:00 정각은 마감)
#   공연 시작 : 12/1
#   현재 시각 : 11/5 (예매 기간 안)
OPENS_AT = datetime(2026, 11, 1, tzinfo=timezone.utc)
CLOSES_AT = datetime(2026, 11, 30, tzinfo=timezone.utc)
STARTS_AT = datetime(2026, 12, 1, tzinfo=timezone.utc)
NOW = datetime(2026, 11, 5, tzinfo=timezone.utc)

ONE_SECOND = timedelta(seconds=1)
ONE_DAY = timedelta(days=1)
EXPIRE_TIME = timedelta(minutes=PENDING_EXPIRE_MINUTES)   # 결제 대기 시간 (5분)

OWNER_ID = 1    # 예매한 본인
OTHER_ID = 2    # 다른 회원


class ReservationTests(unittest.TestCase):

    def setUp(self):
        """각 테스트가 시작되기 직전에 매번 실행된다 (테스트끼리 서로 영향을 주지 않게)"""
        self.ticketholder = TicketHolder(ticketholder_id=OWNER_ID)
        self.performance = ReservedPerformance(
            reserved_perf_id=10,
            perf_starts_at=STARTS_AT,
            reserv_opens_at=OPENS_AT,
            reserv_closes_at=CLOSES_AT,
        )
        self.seat = ReservedSeat(reserved_seat_id=100, reserved_seat_price=Decimal("150000"))
        self.payment = ReservedPayment(reserved_pay_id=1000)

    def make_reservation(self, now=NOW, seat_price=Decimal("150000"), has_active_reservation=False):
        """
        테스트용 예매대기(PENDING) 예매를 만드는 도우미
        - 아무것도 안 넘기면 : 11/5에 15만원 좌석을 예매
        - now, seat_price만 바꿔서 여러 상황을 만든다
        """
        return Reservation.create_pending(
            ticketholder=self.ticketholder,
            performance=self.performance,
            seat=ReservedSeat(reserved_seat_id=100, reserved_seat_price=seat_price),
            has_active_reservation=has_active_reservation,
            now=now,
        )

    def make_confirmed_reservation(self):
        """테스트용 예매확정(CONFIRMED) 예매를 만드는 도우미 (예매대기 → 결제 성공 → 확정)"""
        reservation = self.make_reservation()
        reservation.confirm(self.payment, NOW)
        return reservation

    def make_saved_reservation(self):
        """DB에 저장된 예매대기 예매를 만드는 도우미 (NOW에 생성된 것으로 created_at을 채운다)"""
        reservation = self.make_reservation()
        reservation.created_at = NOW
        return reservation

    # =========================================================
    # 1. 예매 생성
    # =========================================================
    def test_주문번호는_ORD로_시작하고_예매마다_다르다(self):
        first = self.make_reservation()
        second = self.make_reservation()

        self.assertTrue(first.order_number.startswith("ORD-"))
        self.assertNotEqual(first.order_number, second.order_number)

    def test_이미_진행중인_예매가_있으면_예매할_수_없다(self):
        with self.assertRaises(ReservationConflictError) as error : 
            self.make_reservation(has_active_reservation=True)

        self.assertEqual(error.exception.error_code, "RESERVATION_ALREADY_EXISTS")

    def test_새_예매는_대기상태이고_금액은_좌석가격이다(self):
        # 실행
        reservation = self.make_reservation()

        # 확인
        self.assertEqual(reservation.status, ReservationStatus.PENDING)     # 결제 전이라 예매대기
        self.assertEqual(reservation.total_amount, Decimal("150000"))        # 금액 = 좌석 가격
        self.assertEqual(reservation.quantity, 1)                            # 1건 = 1좌석
        self.assertIsNone(reservation.payment)                               # 결제 정보 없음
        self.assertIsNone(reservation.confirmed_at)                          # 아직 확정 안 됨
        self.assertIsNone(reservation.reserv_id)                             # 아직 DB 저장 전
        self.assertIsNone(reservation.canceled_at)                           # 취소 안 됨

    def test_예매_오픈_시각_정각에는_예매된다(self):
        reservation = self.make_reservation(now=OPENS_AT)

        self.assertEqual(reservation.status, ReservationStatus.PENDING)

    def test_예매_오픈_전에는_예매할_수_없다(self):
        # 오픈 1초 전에 예매 시도 -> 예외가 나야 통과
        with self.assertRaises(ReservationConflictError) as error:
            self.make_reservation(now=OPENS_AT - ONE_SECOND)

        # 예외 종류뿐 아니라 오류 코드까지 확인
        self.assertEqual(error.exception.error_code, "RESERVATION_NOT_OPEN")

    def test_예매_마감_시각_정각부터는_예매할_수_없다(self):
        with self.assertRaises(ReservationConflictError) as error:
            self.make_reservation(now=CLOSES_AT)

        self.assertEqual(error.exception.error_code, "RESERVATION_NOT_OPEN")

    def test_0원_좌석은_예매할_수_없다(self):
        with self.assertRaises(ReservationValidationError) as error:
            self.make_reservation(seat_price=Decimal("0"))

        self.assertEqual(error.exception.error_code, "INVALID_TOTAL_AMOUNT")

    def test_음수_금액은_예매할_수_없다(self):
        with self.assertRaises(ReservationValidationError) as error:
            self.make_reservation(seat_price=Decimal("-1"))

        self.assertEqual(error.exception.error_code, "INVALID_TOTAL_AMOUNT")

    def test_좌석_2개는_예매할_수_없다(self):
        # create_pending은 수량을 받지 않으므로, 엔티티를 직접 만들어서 확인
        with self.assertRaises(ReservationValidationError) as error:
            Reservation(
                ticketholder=self.ticketholder,
                performance=self.performance,
                seat=self.seat,
                order_number="ORD-001",
                total_amount=Decimal("150000"),
                status=ReservationStatus.PENDING,
                quantity=2,
            )

        self.assertEqual(error.exception.error_code, "INVALID_QUANTITY")


    # =========================================================
    # 2. 본인 확인
    # =========================================================
    def test_본인_예매인지_확인한다(self):
        reservation = self.make_reservation()
        
        self.assertTrue(reservation.is_owned(OWNER_ID))     # 본인 -> True
        self.assertFalse(reservation.is_owned(OTHER_ID))    # 타인 -> False

    def test_본인은_예매를_조회할_수_있다(self) :
        reservation = self.make_reservation()

        reservation.check_viewable(OWNER_ID)  # 예외가 나지 않으면 통과

    def test_다른_회원은_예매를_조회할_수_없다(self):
        reservation = self.make_reservation()

        with self.assertRaises(ReservationForbiddenError) as error :
            reservation.check_viewable(OTHER_ID)

        self.assertEqual(error.exception.error_code, "RESERVATION_FORBIDDEN")

    # =========================================================
    # 3. 예매 확정 (결제 성공 후)
    # =========================================================
    def test_결제_성공하면_예매가_확정된다(self):
        # 준비
        reservation = self.make_reservation()
        confirm_time = NOW + ONE_SECOND

        # 실행
        reservation.confirm(self.payment, confirm_time)

        # 확인
        self.assertEqual(reservation.status, ReservationStatus.CONFIRMED)   # 확정 상태로 바뀜
        self.assertEqual(reservation.payment, self.payment)                 # 결제 정보 기록
        self.assertEqual(reservation.confirmed_at, confirm_time)            # 확정 일시 기록

    def test_이미_확정된_예매는_다시_확정할_수_없다(self):
        # 준비 : 한 번 확정해 둔다
        reservation = self.make_confirmed_reservation()

        # 실행 : 다른 결제로 한 번 더 확정
        with self.assertRaises(ReservationConflictError) as error:
            reservation.confirm(ReservedPayment(reserved_pay_id=2000), NOW + ONE_DAY)

        # 확인 : 오류가 나고, 처음 결제·확정 일시가 그대로
        self.assertEqual(error.exception.error_code, "RESERVATION_NOT_PENDING")
        self.assertEqual(reservation.payment, self.payment)
        self.assertEqual(reservation.confirmed_at, NOW)

    def test_예매대기_상태는_취소할_수_없다(self):
        # 결제 전(PENDING) 예매는 취소가 아니라 확정만 가능
        reservation = self.make_reservation()

        with self.assertRaises(ReservationConflictError) as error:
            reservation.cancel(OWNER_ID, NOW)

        self.assertEqual(error.exception.error_code, "RESERVATION_NOT_CANCELABLE")
        self.assertEqual(reservation.status, ReservationStatus.PENDING)


    # =========================================================
    # 4. 예매 취소
    # =========================================================
    def test_본인은_공연_전에_취소할_수_있다(self):
        # 준비
        reservation = self.make_confirmed_reservation()
        cancel_time = NOW + ONE_DAY

        # 실행
        reservation.cancel(OWNER_ID, cancel_time)

        # 확인
        self.assertEqual(reservation.status, ReservationStatus.CANCELED)   # 취소 상태로 바뀜
        self.assertEqual(reservation.canceled_at, cancel_time)             # 취소 일시 기록

    def test_공연_시작_1초_전에는_취소할_수_있다(self):
        reservation = self.make_confirmed_reservation()

        reservation.cancel(OWNER_ID, STARTS_AT - ONE_SECOND)

        self.assertEqual(reservation.status, ReservationStatus.CANCELED)

    def test_다른_회원은_취소할_수_없다(self):
        reservation = self.make_confirmed_reservation()

        with self.assertRaises(ReservationForbiddenError) as error:
            reservation.cancel(OTHER_ID, NOW)

        self.assertEqual(error.exception.error_code, "RESERVATION_FORBIDDEN")
        # 취소에 실패했으니 예매는 그대로여야 한다
        self.assertEqual(reservation.status, ReservationStatus.CONFIRMED)
        self.assertIsNone(reservation.canceled_at)

    def test_이미_취소한_예매는_다시_취소할_수_없다(self):
        # 준비 : 한 번 취소해 둔다
        reservation = self.make_confirmed_reservation()
        first_cancel_time = NOW + ONE_DAY
        reservation.cancel(OWNER_ID, first_cancel_time)

        # 실행 : 다음 날 한 번 더 취소
        with self.assertRaises(ReservationConflictError) as error:
            reservation.cancel(OWNER_ID, NOW + ONE_DAY * 2)

        # 확인 : 오류가 나고, 처음 취소한 일시가 그대로 남아 있다
        self.assertEqual(error.exception.error_code, "RESERVATION_NOT_CANCELABLE")
        self.assertEqual(reservation.canceled_at, first_cancel_time)

    def test_공연_시작_시각_정각부터는_취소할_수_없다(self):
        reservation = self.make_confirmed_reservation()

        with self.assertRaises(ReservationConflictError) as error:
            reservation.cancel(OWNER_ID, STARTS_AT)

        self.assertEqual(error.exception.error_code, "PERFORMANCE_ALREADY_STARTED")
        self.assertEqual(reservation.status, ReservationStatus.CONFIRMED)

    # =========================================================
    # 5. VO는 바뀌지 않는다 (frozen=True)
    # =========================================================
    def test_VO_값은_직접_바꿀_수_없다(self):
        reservation = self.make_reservation()

        # 좌석 가격을 바꾸려고 하면 오류
        with self.assertRaises(FrozenInstanceError):
            reservation.seat.reserved_seat_price = Decimal("1")

        # 예매자를 바꾸려고 하면 오류
        with self.assertRaises(FrozenInstanceError):
            reservation.ticketholder.ticketholder_id = OTHER_ID

    # =========================================================
    # 6. 예매대기 만료 (결제 대기 시간 5분)
    # =========================================================
    def test_결제_대기_시간_1초_전에는_만료되지_않는다(self):
        reservation = self.make_saved_reservation()

        self.assertFalse(reservation.is_expired(NOW + EXPIRE_TIME - ONE_SECOND))

    def test_결제_대기_시간_정각부터_만료된다(self):
        reservation = self.make_saved_reservation()

        self.assertTrue(reservation.is_expired(NOW + EXPIRE_TIME))

    def test_DB_저장_전_예매는_만료되지_않는다(self):
        # created_at이 없으면 기준 시각이 없으므로 만료로 보지 않는다
        reservation = self.make_reservation()

        self.assertFalse(reservation.is_expired(NOW + ONE_DAY))

    def test_확정된_예매는_시간이_지나도_만료되지_않는다(self):
        reservation = self.make_saved_reservation()
        reservation.confirm(self.payment, NOW + ONE_SECOND)

        self.assertFalse(reservation.is_expired(NOW + ONE_DAY))

    def test_시간이_지난_예매대기는_만료된다(self):
        # 준비
        reservation = self.make_saved_reservation()

        # 실행
        reservation.expire(NOW + EXPIRE_TIME)

        # 확인
        self.assertEqual(reservation.status, ReservationStatus.EXPIRED)

    def test_시간이_지나지_않은_예매는_만료할_수_없다(self):
        reservation = self.make_saved_reservation()

        with self.assertRaises(ReservationConflictError) as error:
            reservation.expire(NOW + EXPIRE_TIME - ONE_SECOND)

        self.assertEqual(error.exception.error_code, "RESERVATION_NOT_EXPIRABLE")
        self.assertEqual(reservation.status, ReservationStatus.PENDING)   # 그대로

    def test_결제_대기_시간이_지나면_확정할_수_없다(self):
        # 만료 처리가 아직 안 돌았어도(PENDING) 시간이 지났으면 확정 불가
        reservation = self.make_saved_reservation()

        with self.assertRaises(ReservationConflictError) as error:
            reservation.confirm(self.payment, NOW + EXPIRE_TIME)

        self.assertEqual(error.exception.error_code, "RESERVATION_EXPIRED")
        self.assertEqual(reservation.status, ReservationStatus.PENDING)   # 확정 안 됨
        self.assertIsNone(reservation.payment)                           # 결제 정보 기록 안 됨

    def test_만료된_예매는_확정할_수_없다(self):
        # 만료 후 늦게 결제 성공이 와도 확정 불가 -> 결제 쪽에서 환불해야 함
        reservation = self.make_saved_reservation()
        reservation.expire(NOW + EXPIRE_TIME)

        with self.assertRaises(ReservationConflictError) as error:
            reservation.confirm(self.payment, NOW + EXPIRE_TIME + ONE_SECOND)

        self.assertEqual(error.exception.error_code, "RESERVATION_NOT_PENDING")
        self.assertEqual(reservation.status, ReservationStatus.EXPIRED)



if __name__ == "__main__":
    unittest.main()
