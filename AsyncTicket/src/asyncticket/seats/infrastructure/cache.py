"""Redis에는 좌석의 표시 정보만 보관한다. 현재 상태는 DB가 제공한다."""

import asyncio
import json
import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

from asyncticket.seats.domain.enums import SeatGrade

logger = logging.getLogger(__name__)
METADATA_FIELDS = ("perf_seat_id", "seat_id", "perf_id", "grade", "seat_seq", "price")


class RedisSeatListCache:
    """표시 가격은 삭제 실패·동시 저장 시 TTL 동안 이전 값일 수 있다."""

    def __init__(self, client: Redis, *, ttl: int = 10) -> None:
        if ttl <= 0:
            raise ValueError("캐시 만료 시간은 양수여야 합니다.")
        self.client = client
        self.ttl = ttl

    @staticmethod
    def key(perf_id: int) -> str:
        return f"seats:metadata:v1:{perf_id}"

    async def get(self, perf_id: int) -> list[dict[str, object]] | None:
        try:
            async with asyncio.timeout(0.25):
                value = await self.client.get(self.key(perf_id))
            if value is None:
                return None
            items = json.loads(value)
            if not self._valid(items, perf_id):
                logger.warning("좌석 캐시 형식 오류: perf_id=%s", perf_id)
                return None
            return items
        except (RedisError, OSError, TimeoutError, ValueError, TypeError):
            logger.warning("좌석 캐시 조회 실패, DB로 조회: perf_id=%s", perf_id)
            return None

    async def set(self, perf_id: int, items: list[dict[str, object]]) -> None:
        try:
            # 상태·reserv_id는 Redis에 기록하지 않는다.
            metadata = [
                {field: item[field] for field in METADATA_FIELDS} for item in items
            ]
            if not self._valid(metadata, perf_id):
                return
            payload = json.dumps(metadata)
            async with asyncio.timeout(0.25):
                await self.client.set(self.key(perf_id), payload, ex=self.ttl)
        except (RedisError, OSError, TimeoutError, KeyError, TypeError, ValueError):
            logger.warning("좌석 캐시 저장 실패: perf_id=%s", perf_id)

    async def invalidate(self, perf_id: int) -> None:
        try:
            async with asyncio.timeout(0.25):
                await self.client.delete(self.key(perf_id))
        except (RedisError, OSError, TimeoutError):
            logger.warning("좌석 캐시 삭제 실패, TTL로 만료: perf_id=%s", perf_id)

    @staticmethod
    def _valid(items: object, perf_id: int) -> bool:
        if not isinstance(items, list):
            return False
        ids = set()
        for item in items:
            if not isinstance(item, dict) or set(item) != set(METADATA_FIELDS):
                return False
            if any(
                type(item[field]) is not int or item[field] <= 0
                for field in ("perf_seat_id", "seat_id", "perf_id")
            ):
                return False
            if item["perf_id"] != perf_id or item["perf_seat_id"] in ids:
                return False
            ids.add(item["perf_seat_id"])
            if item["grade"] is not None and item["grade"] not in SeatGrade:
                return False
            if item["seat_seq"] is not None and not isinstance(item["seat_seq"], str):
                return False
            if item["price"] is not None and (
                type(item["price"]) is not int or item["price"] < 0
            ):
                return False
        return True
