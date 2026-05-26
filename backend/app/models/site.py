from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import IdMixin, TableNameMixin, TimestampsMixin

if TYPE_CHECKING:
    from app.models.device import Device
    from app.models.organization import Organization


class Site(IdMixin, TimestampsMixin, TableNameMixin, Base):
    """An MSP's client site — a grouping for devices and a scope for RBAC."""

    __tablename__ = "sites"
    __table_args__ = (UniqueConstraint("organization_id", "slug", name="uq_sites_org_slug"),)

    organization_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(63), nullable=False, index=True)
    address: Mapped[str | None] = mapped_column(String(512))
    contact_email: Mapped[str | None] = mapped_column(String(254))
    contact_phone: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(String(2048))

    organization: Mapped[Organization] = relationship("Organization")
    devices: Mapped[list[Device]] = relationship(
        "Device",
        back_populates="site",
        cascade="all, delete-orphan",
    )
