"""좌석 조회용 캐시 계약. 예매 상태와 예매 연결 정보는 보관하지 않는다."""

from typing import Protocol


class SeatListCache(Protocol):
    async def get(self, perf_id: int) -> list[dict[str, object]] | None:
        """등급·좌석명·가격 목록을 반환한다. 미스·장애는 None이다."""
        ...

    async def set(self, perf_id: int, items: list[dict[str, object]]) -> None:
        """조회 결과에서 상태를 제외한 정보만 짧게 보관한다. 장애는 전파하지 않는다."""
        ...

    async def invalidate(self, perf_id: int) -> None:
        """커밋한 회차의 캐시를 삭제한다. 장애는 전파하지 않는다."""
        ...
