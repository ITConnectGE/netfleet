from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import IdMixin, TableNameMixin, TimestampsMixin

if TYPE_CHECKING:
    from app.models.user import User


class Organization(IdMixin, TimestampsMixin, TableNameMixin, Base):
    """The MSP itself. Single-tenant per deployment, but modeled as 1 row for future SaaS mode."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(63), unique=True, nullable=False, index=True)
    is_setup_complete: Mapped[bool] = mapped_column(default=False, nullable=False)

    users: Mapped[list[User]] = relationship(
        "User",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
