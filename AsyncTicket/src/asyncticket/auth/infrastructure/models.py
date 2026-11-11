from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from asyncticket.auth.domain.entities import BlacklistedToken
from asyncticket.shared.core.models import Base


class BlacklistModel(Base):
    __tablename__ = "blacklist"

    jti_token: Mapped[str] = mapped_column(
        String(500),
        primary_key=True,
        nullable=False,
    )

    expired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    def to_domain(self) -> BlacklistedToken:
        return BlacklistedToken(
            jti_token=self.jti_token,
            expired_at=self.expired_at,
        )