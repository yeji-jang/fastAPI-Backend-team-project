from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from asyncticket.shared.core.models import Base
from sqlalchemy.dialects.postgresql import JSONB
from typing import Dict, Any


# 결제 테이블
# - 실패: reserv_id = NULL
# - 성공/환불: reserv_id 필수
# - 취소는 예매에서 시작 → 여기서는 환불 상태로만 기록
class Payment(Base):
    __tablename__ = "payments"


    # 필드이름: Mapped[타입] = mapped_column(DB타입, 제약조건들...)
    # 결제 고유 ID (자동 증가)
    pay_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 성공한 결제에만 연결. 실패 시 NULL (성공 후 예매 원칙)
    # 결제가 성공해야 예매가 생긴다. 실패한 결제는 예매가 없는데 nullable=False는 문제를 불러일으킨다. => nullable=True로 수정.
    reserv_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("reservations.reserv_id"), nullable=True, index=True
    )
    # 외부 결제사 연동 보류로 인한 transaction_ref 제외 처리 
    # transaction_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 결제 수단 (카드, 계좌 등)
    method: Mapped[str] = mapped_column(String(50), nullable=False)
    # 결제 금액
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # 성공 / 실패 / 환불. 취소 결과는 환불로 기록
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    # 결제 시도 생성 시각 (UTC)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    # 성공 상태로 바뀐 시각 (인프라 기록)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 환불 상태로 바뀐 시각 (인프라 기록)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # 결제 로그
    payment_log: Mapped[Dict[str, Any]] = mapped_column(JSONB, server_default="{}",default=dict)