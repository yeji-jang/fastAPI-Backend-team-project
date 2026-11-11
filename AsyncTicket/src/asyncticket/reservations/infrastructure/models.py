from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import BigInteger, Integer, Numeric, String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from asyncticket.shared.core.models import Base # 모든 테이블의 부모


class ReservationModel(Base):
    """예매"""

    # DB에 만들어질 실제 테이블 이름
    __tablename__ = "reservations"

    # Mapped[파이썬 타입] = mapped_column(DB 타입, 옵션들)
    reserv_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True # DB가 알아서 PK 번호를 1씩 증가
    )

    order_number: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    # FK (users.user_id)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id"),
        nullable=False,
        index=True
    )

    # FK (performances.perf_id)
    perf_id: Mapped[int] = mapped_column(
        ForeignKey("performances.perf_id"),
        nullable=False,
        index=True
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # Optianal 기능(| 파이프라인)
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True)

    canceled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True)
