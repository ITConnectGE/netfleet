from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import IdMixin, TableNameMixin, TimestampsMixin

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.refresh_token import RefreshToken
    from app.models.role import RoleAssignment


class AuthMethod(StrEnum):
    LOCAL = "local"
    OIDC = "oidc"


class User(IdMixin, TimestampsMixin, TableNameMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("organization_id", "email", name="uq_users_org_email"),
        UniqueConstraint("oidc_sub", name="uq_users_oidc_sub"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    email: Mapped[str] = mapped_column(String(254), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    mobile_phone: Mapped[str | None] = mapped_column(String(32))

    # local auth
    password_hash: Mapped[str | None] = mapped_column(String(255))
    totp_secret_encrypted: Mapped[str | None] = mapped_column(String(512))
    totp_enrolled: Mapped[bool] = mapped_column(default=False, nullable=False)

    # OIDC auth
    oidc_sub: Mapped[str | None] = mapped_column(String(255), index=True)
    oidc_provider: Mapped[str | None] = mapped_column(String(64))

    auth_method: Mapped[AuthMethod] = mapped_column(
        Enum(AuthMethod, name="auth_method", values_callable=lambda c: [e.value for e in c]),
        default=AuthMethod.LOCAL,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(default=False, nullable=False)

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Watermark for the navbar notifications bell — events with a
    # timestamp greater than this are counted as "unread".
    notifications_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    organization: Mapped[Organization] = relationship("Organization", back_populates="users")
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    role_assignments: Mapped[list[RoleAssignment]] = relationship(
        "RoleAssignment",
        back_populates="user",
        cascade="all, delete-orphan",
    )
