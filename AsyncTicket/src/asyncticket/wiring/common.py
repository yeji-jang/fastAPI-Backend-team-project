"""공연·회차 wiring이 함께 사용하는 요청 세션과 정책 주입 정의."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from asyncticket.shared.core.database import get_db
from asyncticket.shared.domain.catalog import CatalogPolicy

DatabaseSession = Annotated[AsyncSession, Depends(get_db)]


def get_catalog_policy(request: Request) -> CatalogPolicy:
    return request.app.state.catalog_policy
