"""인프라 계층: shows 테이블의 컬럼·타입·외래키를 SQLAlchemy로 매핑한다."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from asyncticket.shared.core.models import Base


class ShowModel(Base):
    __tablename__ = "shows"

    show_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 외래키는 명세 이름을 따른다. 타 담당 테이블을 이 파일에서 새로 정의하지 않는다.
    venues_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("venues.venues_id"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # DB의 NULL 허용 여부와 API에서 입력을 생략할 수 있는지는 별도 규칙이다.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    performer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    runtime: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
