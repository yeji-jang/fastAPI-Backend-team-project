"""
결제 테이블 모델 (SQLAlchemy)
    - payments 테이블의 컬럼 정의. 도메인 엔티티(domain/payment.py)와는 저장소가 서로 바꿔 준다
    - 다른 도메인도 이 모델을 쓴다 → 컬럼을 바꾸면 영향이 퍼진다
        · reservations/infrastructure/repositories.py : 예매 조회 때 pay_id를 outer join
        · tests/reservations/test_reservation_repository.py : 테스트 데이터로 결제 행 생성
    - 이 테이블에는 paymentKey 컬럼이 없다 → payment_log(JSONB)에 함께 보관 (infrastructure/repositories.py)
"""

# <표준 라이브러리>
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any

# <SQLAlchemy>
from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB # 결제 로그 (PostgreSQL 전용)

# <Shared - 팀 공통 모델 부모>
from asyncticket.shared.core.models import Base


# 결제 테이블
# - 실패: reserv_id = NULL
# - 성공/환불: reserv_id 필수
# - 취소는 예매에서 시작 → 여기서는 환불 상태로만 기록
# ※ 2026-11-06 결정으로 흐름이 "예매대기 먼저 → 결제"로 바뀌었다.
#   지금 코드에서는 결제를 만들 때 항상 reserv_id가 있다. nullable=True는 팀 결정으로 유지한다.
class Payment(Base):
    __tablename__ = "payments"


    # 필드이름: Mapped[타입] = mapped_column(DB타입, 제약조건들...)
    # 결제 고유 ID (자동 증가)
    pay_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 성공한 결제에만 연결. 실패 시 NULL (성공 후 예매 원칙)
    # 결제가 성공해야 예매가 생긴다. 실패한 결제는 예매가 없는데 nullable=False는 문제를 불러일으킨다. => nullable=True로 수정.
    # ※ 위 두 줄은 이전 흐름(결제 성공 후 예매) 기준의 기록. 지금은 예매가 먼저라 결제는 항상 예매에 연결된다.
    reserv_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("reservations.reserv_id"), nullable=True, index=True
    )
    # 외부 결제사 연동 보류로 인한 transaction_ref 제외 처리
    # transaction_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 결제 수단 (카드, 계좌 등)
    # ※ NOT NULL이라 승인 전에는 "TOSS"를 넣고, 승인 후 토스가 준 수단으로 바꾼다 (domain/payment.py)
    method: Mapped[str] = mapped_column(String(50), nullable=False)
    # 결제 금액
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # 성공 / 실패 / 환불. 취소 결과는 환불로 기록
    # ※ 저장 값: READY / DONE / FAIL / REFUND (domain/enums.py)
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
    # ※ 저장 모양: {"payment_key": "<토스 paymentKey>", "logs": [<토스 응답>, ...]}
    # ※ dev 브랜치 모델에는 없는 컬럼이다. dev로 만든 DB에는 ALTER TABLE이 필요하다.
    payment_log: Mapped[Dict[str, Any]] = mapped_column(JSONB, server_default="{}",default=dict)
