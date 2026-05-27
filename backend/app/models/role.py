from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import IdMixin, TableNameMixin, TimestampsMixin

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.user import User


class PermissionAction(StrEnum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"


class AssignmentScope(StrEnum):
    ORGANIZATION = "organization"
    TENANT = "tenant"
    SITE = "site"
    DEVICE = "device"


class Role(IdMixin, TimestampsMixin, TableNameMixin, Base):
    """A named bundle of permissions, scoped to an organization."""

    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_roles_org_name"),)

    organization_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(String(512))
    is_system: Mapped[bool] = mapped_column(default=False, nullable=False)

    organization: Mapped[Organization] = relationship("Organization")
    permissions: Mapped[list[Permission]] = relationship(
        "Permission",
        back_populates="role",
        cascade="all, delete-orphan",
    )
    assignments: Mapped[list[RoleAssignment]] = relationship(
        "RoleAssignment",
        back_populates="role",
        cascade="all, delete-orphan",
    )


class Permission(IdMixin, Base):
    """A single (section, action) grant attached to a role."""

    __tablename__ = "permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "section", "action", name="uq_permissions_role_section_action"),
    )

    role_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[PermissionAction] = mapped_column(
        Enum(PermissionAction, name="permission_action", values_callable=lambda c: [e.value for e in c]), nullable=False
    )

    role: Mapped[Role] = relationship("Role", back_populates="permissions")


class RoleAssignment(IdMixin, TimestampsMixin, TableNameMixin, Base):
    """Binds a user to a role, scoped to the org / a site / a single device."""

    __tablename__ = "role_assignments"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "role_id", "scope_type", "scope_id", name="uq_role_assignments_unique"
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scope_type: Mapped[AssignmentScope] = mapped_column(
        Enum(AssignmentScope, name="assignment_scope", values_callable=lambda c: [e.value for e in c]),
        nullable=False,
        default=AssignmentScope.ORGANIZATION,
    )
    scope_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), index=True)

    user: Mapped[User] = relationship("User", back_populates="role_assignments")
    role: Mapped[Role] = relationship("Role", back_populates="assignments")
