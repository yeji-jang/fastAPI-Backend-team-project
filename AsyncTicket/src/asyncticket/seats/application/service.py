from datetime import datetime, timezone

from asyncticket.seats.domain.repository import (
    PerformanceSeatRepository,
    SeatInfoRepository,
    SeatLookupConflictError,
)
from asyncticket.seats.domain.seat_info import SeatInfo, SeatManagement
from asyncticket.seats.domain.enums import SeatGrade
from asyncticket.seats.domain.performance_seat import (
    SeatIdentity,
    SeatReservationChange,
    SeatReservationConflictError,
)
from asyncticket.seats.application.exceptions import (
    SeatInfoNotFoundError,
    PerformanceNotFoundError,
    SeatNotFoundError,
    ReservationSeatsNotFoundError,
    SeatLookupIntegrityError,
    ReservationSeatIntegrityError,
)
from asyncticket.shared.domain.catalog import CatalogActor, CatalogPolicy


class SeatInfoService:
    """좌석 등급 생성·가격 변경의 실행 순서를 조정한다.

    구성·가격 규칙은 SeatInfo가 판단하고, 저장소가 조회·저장을 담당한다.
    등급과 개별 좌석은 같은 트랜잭션에서 저장한다.
    """

    def __init__(
        self,
        repository: SeatInfoRepository,
        performance_seat_repository: PerformanceSeatRepository,
        policy: CatalogPolicy,
    ) -> None:
        self.repository = repository
        self.performance_seat_repository = performance_seat_repository
        self.policy = policy

    async def get_seat_info(self, seat_id: int) -> SeatInfo:
        seat_info = await self.repository.get_seat_info(seat_id)
        if seat_info is None:
            raise SeatInfoNotFoundError("좌석 등급을 찾을 수 없습니다.")
        return seat_info

    async def _authorize(self, perf_id: int, actor: CatalogActor) -> None:
        self.policy.authorize(actor)
        if not await self.repository.lock_performance(perf_id):
            raise PerformanceNotFoundError("공연 회차를 찾을 수 없습니다.")
        context = await self.repository.get_management_context(perf_id)
        if context is None:
            raise PerformanceNotFoundError("공연 회차를 찾을 수 없습니다.")
        management = SeatManagement(
            owner_id=context["owner_id"],
            booking_opens_at=context["booking_opens_at"],
        )
        management.authorize_change(actor, self.policy, now=datetime.now(timezone.utc))

    async def create(
        self,
        *,
        perf_id: int,
        name: SeatGrade,
        total_seat: int,
        price: int,
        seat_seqs: list[str],
        actor: CatalogActor,
    ) -> SeatInfo:
        """입력값으로 등급을 만들고 개별 좌석과 함께 저장한다."""
        try:
            seat_info = SeatInfo.create(
                perf_id=perf_id,
                name=name,
                total_seat=total_seat,
                price=price,
            )
            await self._authorize(perf_id, actor)
            names = seat_info.require_new_configuration(seat_seqs)

            seat_info.require_unique_grade(
                await self.repository.grade_exists(seat_info.perf_id, seat_info.name)
            )
            seat_info.require_unique_seat_names(
                await self.performance_seat_repository.names_exist(
                    seat_info.perf_id, list(names.values)
                )
            )

            saved_grade = await self.repository.save_seat_info(seat_info)
            await self.performance_seat_repository.save_many(
                saved_grade.create_seats(names)
            )
            await self.repository.commit()
            return saved_grade
        except BaseException:
            await self.repository.rollback()
            raise

    async def update_price(
        self,
        perf_id: int,
        seat_id: int,
        price: int,
        actor: CatalogActor,
    ) -> SeatInfo:
        try:
            # _authorize가 회차를 잠근 뒤 최신 등급을 조회한다.
            await self._authorize(perf_id, actor)
            current = await self.get_seat_info(seat_id)
            changed = current.update_price(price, perf_id=perf_id)
            saved_grade = await self.repository.save_seat_info(changed)
            await self.repository.commit()
            return saved_grade
        except BaseException:
            await self.repository.rollback()
            raise


class PerformanceSeatService:
    """개별 좌석 조회·예매 연결 서비스."""

    def __init__(
        self,
        repository: PerformanceSeatRepository,
        seat_info_repository: SeatInfoRepository,
    ) -> None:
        self.repository = repository
        self.seat_info_repository = seat_info_repository

    async def _require_performance(self, perf_id: int) -> None:
        if not await self.seat_info_repository.performance_exists(perf_id):
            raise PerformanceNotFoundError("공연 회차를 찾을 수 없습니다.")

    async def list_performance_seats(self, perf_id: int) -> list[dict[str, object]]:
        await self._require_performance(perf_id)
        return await self.repository.list_performance_seats(perf_id)

    async def get_seat_info(self, perf_id: int, seat_id: int) -> dict[str, object]:
        grade = await self.seat_info_repository.get_seat_info_view(perf_id, seat_id)
        if grade is None:
            raise SeatInfoNotFoundError("해당 회차의 좌석 등급을 찾을 수 없습니다.")
        return grade

    async def get_performance_seat(
        self, perf_id: int, seat_seq: str
    ) -> dict[str, object]:
        await self._require_performance(perf_id)
        try:
            seat = await self.repository.get_performance_seat(perf_id, seat_seq)
        except SeatLookupConflictError as exc:
            raise SeatLookupIntegrityError("좌석 정보를 확인할 수 없습니다.") from exc
        if seat is None:
            raise SeatNotFoundError("해당 회차의 좌석을 찾을 수 없습니다.")
        return seat

    async def get_reservation_seats(
        self, reserv_id: int, user_id: int
    ) -> dict[str, object]:
        try:
            reservation = await self.repository.get_owned_reservation_seats(
                reserv_id, user_id
            )
        except SeatLookupConflictError as exc:
            raise ReservationSeatIntegrityError(
                "예매 좌석 정보를 확인할 수 없습니다."
            ) from exc
        if reservation is None:
            raise ReservationSeatsNotFoundError("예매 좌석을 찾을 수 없습니다.")
        return reservation

    async def assign_reservation(
        self,
        *,
        perf_id: int,
        perf_seat_id: int,
        reserv_id: int,
        expected_status: str,
        reserved_status: str,
    ) -> None:
        """예매와 같은 세션으로 연결한다. 상태값과 최종 commit은 호출부가 맡는다."""
        change = SeatReservationChange.assign(
            perf_id=perf_id,
            perf_seat_id=perf_seat_id,
            reserv_id=reserv_id,
            expected_status=expected_status,
            reserved_status=reserved_status,
        )
        linked = await self.repository.assign_reservation(
            perf_id=change.perf_id,
            perf_seat_id=change.perf_seat_id,
            reserv_id=change.reserv_id,
            expected_status=change.expected_status,
            reserved_status=change.target_status,
        )
        change.require_applied(linked)

    async def get_performance_seat_by_id(
        self,
        *,
        perf_id: int,
        perf_seat_id: int,
    ) -> dict[str, object]:
        """가격·상태 조회. 조회 성공은 좌석 선점을 뜻하지 않는다."""
        identity = SeatIdentity(perf_id=perf_id, perf_seat_id=perf_seat_id)
        await self._require_performance(identity.perf_id)
        seat = await self.repository.get_performance_seat_by_id(
            identity.perf_id, identity.perf_seat_id
        )
        if seat is None:
            raise SeatNotFoundError("해당 회차의 좌석을 찾을 수 없습니다.")
        return seat

    async def release_reservation(
        self,
        *,
        perf_id: int,
        perf_seat_id: int,
        reserv_id: int,
        expected_status: str,
        released_status: str,
    ) -> None:
        """현재 예매 연결만 해제한다. 다른 예매로 바뀐 좌석은 해제하지 않는다.

        취소 판단·상태값·최종 commit은 호출부가 맡고 같은 세션을 공유한다.
        """
        # 미리 조회한 ORM 객체가 있으면 호출부에서 refresh한 뒤 사용한다.
        change = SeatReservationChange.release(
            perf_id=perf_id,
            perf_seat_id=perf_seat_id,
            reserv_id=reserv_id,
            expected_status=expected_status,
            released_status=released_status,
        )
        released = await self.repository.release_reservation(
            perf_id=change.perf_id,
            perf_seat_id=change.perf_seat_id,
            reserv_id=change.reserv_id,
            expected_status=change.expected_status,
            released_status=change.target_status,
        )
        change.require_applied(released)
