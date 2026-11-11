"""인프라 계층: performances 테이블과 공연 FK를 매핑한다."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from asyncticket.shared.core.models import Base


class PerformanceModel(Base):
    __tablename__ = "performances"

    perf_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    show_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shows.show_id"), nullable=False
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # TIMESTAMPTZ에 대응한다. API는 시간대가 포함된 시각만 입력으로 받는다.
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    booking_opens_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    booking_closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # 현재 ERD의 기본값 3을 보존한다. 판매 매수 정책 변경은 별도 합의가 필요하다.
    max_tickets_per_user: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("3")
    )
    # SCHEDULED는 명세 예시다. 팀이 정하지 않은 DB Enum을 추가하지 않는다.
    status: Mapped[str] = mapped_column(String(30), nullable=False)
