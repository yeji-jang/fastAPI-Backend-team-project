"""
예매 응용 서비스 (순서 조율)
    1. 
        - 규칙 판단은 예매 엔티티(domain)가 하고, 응용계층에서는 순서대로 호출만 한다
        - commit은 하지 않고 요청이 끝날 때 get_db가 commit (중간에 실패하면 전체 rollback)
    2. 예매하기(순서) :
        1) 1인 1건 확인
        2) 회차 및 좌석 조회
        3) 예매대기 생성
        4) reserv_id DB 저장
        5) 좌석 연결
    3. 결제 후 확정(순서) :
        1) 예매 조회
        2) 예매 확정
        3) 상태 저장
    4. 예매 취소(순서) : 
        1) 예매 조회
        2) 예매 취소
        3) 상태 저장
        4) 좌석 해제
    5. 예매 조회 (본인 예매 단건, 목록)
        1) 예매 조회
        2) 본인 예매만 조회
    6. 예매대기 만료(순서) :
        1) 만료 대상 조회 (지금 - 결제 대기 시간 이전에 생성된 예매대기)
        2) 예매 만료
        3) 상태 저장
        4) 좌석 해제
"""
from datetime import datetime, timedelta, timezone

# <Domain - 예매>
from asyncticket.reservations.domain.repository import ReservationRepository
from asyncticket.reservations.domain.reservation import(
    Reservation,
    TicketHolder,
    ReservedPayment,
    ReservationNotFoundError,
    PENDING_EXPIRE_MINUTES,
)
from asyncticket.reservations.domain.service import (
    ReservationChecker,
    ReservedPerformanceReader,
    ReservedSeatReader
)

# <Application - 예매>
from asyncticket.reservations.application.ports import SeatAllocation


class ReservationService:
    """예매 서비스"""

    def __init__(
        self,
        repository : ReservationRepository,
        checker : ReservationChecker,
        performance_reader : ReservedPerformanceReader,
        seat_reader : ReservedSeatReader,
        seat_allocation : SeatAllocation,
    ) : 
        self.repository = repository
        self.checker = checker
        self.performance_reader = performance_reader
        self.seat_reader = seat_reader
        self.seat_allocation = seat_allocation


    # 예매 ID로 조회, 없으면 404 (확정·취소·조회 공통)
    async def _get_reservation(self, reserv_id: int) -> Reservation :
        reservation = await self.repository.find_by_reserv_id(reserv_id)
        if reservation is None :
            raise ReservationNotFoundError(
                message="예매를 찾을 수 없습니다",
                error_code="RESERVATION_NOT_FOUND")
        return reservation

    # 좌석 해제 (좌석 연결이 남아 있을 때만, 취소, 만료 공통으로!)
    async def _release_seat(self, reservation : Reservation) -> None :
        if reservation.seat.reserved_seat_id is None :
            return
        await self.seat_allocation.release(
            perf_id=reservation.performance.reserved_perf_id,
            perf_seat_id=reservation.seat.reserved_seat_id,
            reserv_id=reservation.reserv_id,
        )

    # 2. 예매하기 : 예매대기(PENDING)로 저장하고 좌석을 잡는다
    async def reserve(
        self,
        *,
        ticketholder_id : int,
        perf_id : int,
        perf_seat_id : int,
        now : datetime | None = None,
    ) -> Reservation :
        now = now or datetime.now(timezone.utc)


        # 1) 1인 1건 확인 (있는지만 조회, 판단은 엔티티가)
        has_active = not await self.checker.is_reserv_possible(ticketholder_id, perf_id)

        # 2) 회차 및 좌석 조회
        # 회차
        performance = await self.performance_reader.get_reserved_performance(perf_id)

        if performance is None : 
            raise ReservationNotFoundError(
                message="공연 회차를 찾을 수 없습니다",
                error_code="PERFORMANCE_NOT_FOUND")

        # 좌석
        seat = await self.seat_reader.get_reserved_seat(perf_id, perf_seat_id)

        if seat is None : 
            raise ReservationNotFoundError(
                message="해당 회차의 좌석을 찾을 수 없습니다",
                error_code="SEAT_NOT_FOUND")


        # 3) 예매대기 생성 (예매 기간, 금액, 1인 1건 규칙은 엔티티가 판단)
        reservation = Reservation.create_pending(
            ticketholder=TicketHolder(ticketholder_id=ticketholder_id),
            performance=performance,
            seat=seat,
            has_active_reservation=has_active,
            now=now,
        )

        # 4) 저장 -> DB가 reserv_id 생성
        reservation = await self.repository.reserv_add(reservation)

        # 5) 좌석 연결 (이미 팔린 좌석이면 좌석 쪽에서 409 -> 전체 Rollback)
        await self.seat_allocation.hold(
            perf_id=perf_id,
            perf_seat_id=perf_seat_id,
            reserv_id=reservation.reserv_id,
        )

        return reservation

    # 3. 결제 후 확정 : 예매대기(PENDING) → 예매확정(CONFIRMED)
    async def confirm(
        self,
        *,
        reserv_id : int,
        pay_id : int,
        now : datetime | None = None,
    ) -> Reservation : 
        now = now or datetime.now(timezone.utc)

        # 1) 예매 조회 (없으면 404)
        reservation = await self._get_reservation(reserv_id)

        # 2) 확정 (예매대기 상태인지는 엔터티가 판단)
        reservation.confirm(ReservedPayment(reserved_pay_id=pay_id), now)

        # 3) 상태 저장 (status, confirmed_at)
        await self.repository.reserv_status_update(reservation)
        return reservation 

    
    # 4. 예매 취소 : 예매확정(CONFIRMED) → 예매취소(CANCELED), 좌석 해제
    async def cancel(
        self,
        *,
        reserv_id : int, 
        ticketholder_id : int,
        now : datetime | None = None,    
    ) -> Reservation : 
        now = now or datetime.now(timezone.utc)

        # 1) 예매 조회 (없으면 404)
        reservation = await self._get_reservation(reserv_id)

        # 2) 예매 취소 (본인 확인·확정 상태·공연 시작 전인지는 엔티티가 판단)
        reservation.cancel(ticketholder_id, now)

        # 3) 상태 저장 (status, canceled_at)
        await self.repository.reserv_status_update(reservation)

        # 4) 좌석 해제 (좌석 연결이 남아 있을 때만)
        await self._release_seat(reservation)
        
        return reservation

    # 5-1. 예매 조회 : 본인 예매 단건
    async def get_reservation(
        self,
        *,
        reserv_id : int, 
        ticketholder_id : int,
    ) -> Reservation : 
        
        # 1) 예매 조회 (없으면 404)
        reservation = await self._get_reservation(reserv_id)

        # 2) 본인 예매만 조회 (본인 확인은 엔티티가 판단)
        reservation.check_viewable(ticketholder_id)

        return reservation

    # 5-2. 예매 조회 : 내 예매 목록 (최신순, 없으면 빈 리스트)
    async def list_reservations(
        self, 
        *,
        ticketholder_id : int,
    ) -> list[Reservation] : 
        return await self.repository.find_all_by_ticketholder(ticketholder_id)

    # 6. 예매대기 만료 : 결제 대기 시간이 지난 예매대기(PENDING) -> 예매만료(EXPIRED), 좌석해제
    async def expire_pending(
        self,
        *,
        now : datetime | None = None,
    ) -> list[Reservation] : 
        now = now or datetime.now(timezone.utc)

        # 1) 만료 대상 조회 (기준 시각 = 지금 - 결제 대기 시간)
        before = now - timedelta(minutes=PENDING_EXPIRE_MINUTES)
        reservations = await self.repository.find_pending_created_before(before)

        for reservation in reservations :
            # 2) 만료 시간이 지났는지 엔티티가 한번 더 판단
            reservation.expire(now)

            # 3) 상태 저장 (status)
            await self.repository.reserv_status_update(reservation)

            # 4) 좌석 해제 
            await self._release_seat(reservation)

        return reservations