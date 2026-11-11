from datetime import date, datetime


from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Identity,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from asyncticket.shared.core.models import Base
from asyncticket.users.domain.users import User, UserRole


class UserModel(Base):
    __tablename__ = "users"

    __table_args__ = (
        CheckConstraint(
            "role IN ('ADMIN', 'SELLER', 'BUYER')",
            name="ck_users_role",
        ),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(),
        primary_key=True,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'BUYER'"),
    )

    phone_number: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    birth: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    address: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    address_detail: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    post_no: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=func.now(),
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def to_domain(self) -> User:
        return User(
            user_id=self.user_id,
            email=self.email,
            name=self.name,
            password_hash=self.password_hash,
            role=UserRole(self.role),
            phone_number=self.phone_number,
            birth=self.birth,
            address=self.address,
            address_detail=self.address_detail,
            post_no=self.post_no,
            created_at=self.created_at,
            updated_at=self.updated_at,
            deleted_at=self.deleted_at,
        )