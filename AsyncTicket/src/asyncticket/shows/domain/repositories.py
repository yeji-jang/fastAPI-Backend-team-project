"""도메인 계층의 저장소 인터페이스: 응용 서비스가 요구하는 기능만 정의한다."""

from typing import Protocol

from asyncticket.shows.domain.show import Show, ShowQuery


class ShowRepository(Protocol):
    async def find_by_id(self, show_id: int, *, for_update: bool = False) -> Show | None: ...

    async def find_all(self, query: ShowQuery) -> tuple[list[Show], int]: ...

    async def create(self, values: dict[str, object]) -> Show: ...

    async def update(self, show_id: int, values: dict[str, object]) -> Show: ...

    async def delete(self, show_id: int) -> None: ...
