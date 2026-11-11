"""회차 서비스와 공연 서비스가 같은 요청 DB 세션을 사용하도록 조립한다."""

from typing import Annotated

from fastapi import Depends, FastAPI

from asyncticket.performances.application.service import PerformanceApplicationService
from asyncticket.performances.infrastructure.adapter_show import ShowServiceAdapter
from asyncticket.performances.infrastructure.repositories import SqlAlchemyPerformanceRepository
from asyncticket.shared.domain.catalog import CatalogPolicy
from asyncticket.shared.infrastructure.catalog import (
    SqlAlchemyCatalogRelations, SqlAlchemyCatalogUnitOfWork,
)
from asyncticket.shows.application.service import ShowApplicationService
from asyncticket.wiring.common import DatabaseSession, get_catalog_policy
from asyncticket.wiring.shows import provide_show_service


def provide_performance_service() -> PerformanceApplicationService:
    raise NotImplementedError("PerformanceApplicationService 의존성이 주입되지 않았습니다.")


def create_performance_service(
    session: DatabaseSession,
    show_service: Annotated[ShowApplicationService, Depends(provide_show_service)],
    policy: Annotated[CatalogPolicy, Depends(get_catalog_policy)],
) -> PerformanceApplicationService:
    # 같은 요청 세션의 기존 공연 서비스를 어댑터로 감싸며 새 세션/commit을 만들지 않는다.
    return PerformanceApplicationService(
        SqlAlchemyPerformanceRepository(session), ShowServiceAdapter(show_service),
        SqlAlchemyCatalogRelations(session), SqlAlchemyCatalogUnitOfWork(session), policy,
    )


def wire_dependencies(app: FastAPI) -> None:
    app.dependency_overrides[provide_performance_service] = create_performance_service
