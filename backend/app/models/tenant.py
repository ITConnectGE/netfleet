"""Tenant — the MSP's customer (a single client that may have many sites).

Hierarchy: Organization (the MSP) → Tenant (the customer) → Site → Device.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import IdMixin, TableNameMixin, TimestampsMixin

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.site import Site


class Tenant(IdMixin, TimestampsMixin, TableNameMixin, Base):
    """A customer of the MSP. Holds one-to-many sites."""

    __tablename__ = "tenants"
    __table_args__ = (UniqueConstraint("organization_id", "slug", name="uq_tenants_org_slug"),)

    organization_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(63), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(1024))

    primary_contact_name: Mapped[str | None] = mapped_column(String(255))
    primary_contact_email: Mapped[str | None] = mapped_column(String(254))
    primary_contact_phone: Mapped[str | None] = mapped_column(String(64))

    organization: Mapped[Organization] = relationship("Organization")
    sites: Mapped[list[Site]] = relationship(
        "Site",
        back_populates="tenant",
        cascade="all, delete-orphan",
    )
