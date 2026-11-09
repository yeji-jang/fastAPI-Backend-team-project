from datetime import datetime, timezone
from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# 데이터베이스 테이블의 기준(베이스 클래스) 정의
class Base(DeclarativeBase):
    pass

# 튜터 공통 시각 믹스인. 팀 모델에 상속시키거나 ERD 컬럼을 변경하지는 않는다.
class DateTimeBase:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now(timezone.utc), nullable=False
    )
    modified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, onupdate=datetime.now(timezone.utc), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, nullable=True
    )

# 모델 초기화
def init_models():
    """SQLAlchemy 모델 메타데이터 등록"""
    import asyncticket.shows.infrastructure.models
    import asyncticket.performances.infrastructure.models
    import asyncticket.seats.infrastructure.models
    import asyncticket.payment.infrastructure.models
    import asyncticket.reservations.infrastructure.models
    import asyncticket.users.infrastructure.models
    import asyncticket.venues.infrastructure.models
    import asyncticket.auth.infrastructure.models
