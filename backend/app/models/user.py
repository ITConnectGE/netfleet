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

    # SMS / email one-time-code at login. Independent of TOTP; when both
    # are configured TOTP wins (per the user's "ჯერ აგდებდეს two
    # factor-ს" rule in P21 #17). Code is hashed; plaintext only
    # appears in the dispatched SMS/email.
    otp_login_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    otp_code_hash: Mapped[str | None] = mapped_column(String(255))
    otp_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    otp_attempts: Mapped[int] = mapped_column(default=0, nullable=False)

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
    # Set to True when an admin auto-generates an invite password or
    # resets a user's password. The dashboard layout intercepts users
    # with this flag and walks them through a password change before
    # anything else can be done.
    must_change_password: Mapped[bool] = mapped_column(default=False, nullable=False)

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
