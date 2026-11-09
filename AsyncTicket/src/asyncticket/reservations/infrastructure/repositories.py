"""
예매 저장소 구현 
    - domain/repository.py의 약속을 SQLAlchemy로 구현
        1) 예매를 저장 (예매생성은 reservation.py-Reservation에서)
        2) 예매 ID로 찾고
        3) 회원의 예매 목록을 찾고
        4) 바뀐 상태(취소, 확정, 만료)를 저장
        5) 만료 대상 예매대기 목록을 찾는다
    - commit은 하지 않는다 : 
        - 요청이 끝날 때 get_db가 commit
        - 예매 저장 → 좌석 연결 → 결제 처리를 한 트랜잭션으로 묶기 위해 flush만 한다
"""
from datetime import datetime

# <sqlalchemy>
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# <Domain - 예매>
from asyncticket.reservations.domain.enums import ReservationStatus # 예매상태
from asyncticket.reservations.domain.repository import ReservationRepository # (추상)예매 저장소
from asyncticket.reservations.domain.reservation import (Reservation, TicketHolder, ReservedPerformance, ReservedSeat, ReservedPayment) # 예매 엔터티&VO

# <InfraStructure - 예매, 좌석, 결제, 공연좌석, 공연>
from asyncticket.reservations.infrastructure.models import ReservationModel # 예매 모델 - 예매 테이블의 속성
from asyncticket.payment.infrastructure.models import Payment as PaymentModel # 결제 모델
# from asyncticket.seats.infrastructure.models import SeatsInfoModel # 좌석 모델
from asyncticket.seats.infrastructure.models import PerformanceSeats # 공연좌석 모델
from asyncticket.performances.infrastructure.models import PerformanceModel # 공연 모델


class SqlAlchemyReservationRepository(ReservationRepository):

    def __init__(self, session: AsyncSession):
        self.session = session


    # 1) 예매 저장 
    async def reserv_add(self, 
                        reservation:Reservation) -> Reservation:
        """1) 예매 저장후 reserv_id가 채워진 예매를 돌려준다"""

        """엔티티  → ReservationModel (DB 저장할 때)"""
        row = ReservationModel(
            # models.py 속성명 = reservation.py 엔터티.속성명

            # reserv_id는 예매생성 성공 후 db 저장시 처리!
            order_number = reservation.order_number,
            user_id = reservation.ticketholder.ticketholder_id,
            perf_id = reservation.performance.reserved_perf_id,
            quantity = reservation.quantity,
            total_amount = reservation.total_amount,
            status = reservation.status.value,  # ReservationStatus의 실제 값
            # created_at는 예매생성 성공 후 db 저장시 처리!
            confirmed_at = reservation.confirmed_at,
            canceled_at = reservation.canceled_at,
        )

        # DB에 보내지 않고 세션에만 올려두는 작업이라 await은 제외
        self.session.add(row) 

        # INSERT만 보내서 DB가 만든 reserv_id, created_at을 받는다
        # 예매생성 실패 시 Rollback이 가능하도록 commit이 아닌 flush로 처리!
        await self.session.flush()

        # DB가 만든 값을 엔터티에 채워서 돌려줌
        reservation.reserv_id = row.reserv_id
        reservation.created_at = row.created_at
        return reservation


    # 2) 예매 ID로 찾음
    async def find_by_reserv_id(self, 
                                reserv_id : int) -> Reservation | None :
        """2) 예매 ID 찾기 없으면 None 반환"""
        # ① SQL 문장 조립 (statement : DB에 보낼 문장)
        statement = (
            self._select_reservations()
            .where(ReservationModel.reserv_id == reserv_id)
        )
        # ② DB에서 실행
        result = await self.session.execute(statement) 
        # ③ 첫 줄 꺼내기 (없으면 None) - 예매 ID는 PK라서 한줄만 조회
        row = result.first()
        # ④ 있으면 엔티티로, 없으면 None (row → 엔티티(꺼낼 때))
        return self._to_entity(row) if row else None


    # 3) 회원의 예매 목록을 찾고
    async def find_all_by_ticketholder(self, 
                                        ticketholder_id: int) -> list[Reservation] :
        """3) 회원의 예매 목록을 찾기 없으면 빈리스트[]를 반환"""
        # ① SQL 문장 조립 : 공통 SELECT에 조건만 회원 ID로, 최신 예매부터
        statement = (
            self._select_reservations()
            .where(ReservationModel.user_id == ticketholder_id)
            .order_by(ReservationModel.created_at.desc())
        )
        # ② DB에서 실행
        result = await self.session.execute(statement)
        # ③ 모든 줄 꺼내기 (없으면 빈 리스트)
        rows = result.all()
        # ④ 줄마다 엔티티로 변환
        return [self._to_entity(row) for row in rows]


    # 4) 바뀐 상태(확정,취소)를 저장
    async def reserv_status_update(self, 
                                   reservation:Reservation) -> None :
        """4) 예매 상태 변경(확정, 취소)을 저장"""
        # ① 저장할 예매 행을 DB에서 찾기 (예매 테이블만 있으면 되므로 JOIN 없이)
        statement = (
            select(ReservationModel)
            .where(ReservationModel.reserv_id == reservation.reserv_id)
        )
        result = await self.session.execute(statement)
        row = result.scalar_one_or_none()
        if row is None : 
            raise LookupError(f"저장할 예매가 없습니다: reserv_id={reservation.reserv_id}")

        # ② 엔티티(confirm()·cancel()로 바뀐 값) → DB 행에 옮기기
        row.status = reservation.status.value       # enum -> DB문자열
        row.confirmed_at = reservation.confirmed_at   # 확정 일시 (확정 시)
        row.canceled_at = reservation.canceled_at     # 취소 일시 (취소 시)

        # ③ UPDATE만 보내기 (commit은 get_db가 함)
        await self.session.flush()


    # 5) 만료 대상 예매대기 목록을 찾고
    async def find_pending_created_before(self,
                                          before : datetime) -> list[Reservation] :
        """5) before 이전에 생성된 예매대기(PENDING) 목록찾기, 없으면 빈리스트[]"""
        # ① SQL 문장 조립 : 예매대기 상태 + 생성 시각이 before 이전
        statement = (
            self._select_reservations()
            .where(
                ReservationModel.status == ReservationStatus.PENDING.value,
                ReservationModel.created_at <= before,
            )
        )

        # ② DB에서 실행
        result = await self.session.execute(statement)

        # ③ 줄마다 엔티티로 변환
        return [self._to_entity(row) for row in result.all()]


    # ----------조회(select)를 도와주는 함수 구현----------
    def _select_reservations(self):
        """(Join) 예매 + 회차 + 공연좌석 + 결제 정보를 한번에 가져옴
        예매·회차·좌석·결제 4개 테이블을 합치는 SELECT 문장을 만들어 돌려줌"""
        return (
            select(
                ReservationModel,
                PerformanceModel.starts_at,
                PerformanceModel.booking_opens_at,
                PerformanceModel.booking_closes_at,
                PerformanceSeats.perf_seat_id,
                PaymentModel.pay_id
            )
            # join(INNER JOIN) : 반드시 있어야 함!
            .join(PerformanceModel, PerformanceModel.perf_id == ReservationModel.perf_id)

            # outerjoin(LEFT OUTER JOIN) : 있을 수도 없을 있음 (null 허용)
            .outerjoin(PerformanceSeats, PerformanceSeats.reserv_id == ReservationModel.reserv_id)
            .outerjoin(PaymentModel, PaymentModel.reserv_id == ReservationModel.reserv_id)
        )

    def _to_entity(self, row) -> Reservation:
        """row(DB 모양)를 Reservation(도메인 모양)으로 바꿔준다"""
        reserv_model = row.ReservationModel
        return Reservation(
            reserv_id=reserv_model.reserv_id,
            ticketholder=TicketHolder(ticketholder_id=reserv_model.user_id),
            order_number=reserv_model.order_number,
            total_amount=reserv_model.total_amount,
            status=ReservationStatus(reserv_model.status), # DB 문자열 → enum
            quantity=reserv_model.quantity,
            created_at=reserv_model.created_at,
            confirmed_at=reserv_model.confirmed_at,
            canceled_at=reserv_model.canceled_at,

            # 공연
            performance=ReservedPerformance(
                reserved_perf_id=reserv_model.perf_id,
                perf_starts_at=row.starts_at,
                reserv_opens_at=row.booking_opens_at,
                reserv_closes_at=row.booking_closes_at
            ),

            # 좌석
            seat=ReservedSeat(
                reserved_seat_id=row.perf_seat_id,
                reserved_seat_price=reserv_model.total_amount, # 구매 당시 가격
            ),

            # 결제
            payment=ReservedPayment(
                reserved_pay_id=row.pay_id
            )
        )
