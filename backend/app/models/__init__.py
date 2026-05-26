"""SQLAlchemy ORM models — importing this module registers all tables on Base.metadata."""

from app.core.database import Base
from app.models.audit_log import AuditLog, AuditOutcome
from app.models.device import Device, DeviceStatus, DeviceTransport
from app.models.device_backup import BackupSource, BackupStatus, DeviceBackup
from app.models.organization import Organization
from app.models.refresh_token import RefreshToken
from app.models.role import AssignmentScope, Permission, PermissionAction, Role, RoleAssignment
from app.models.secret_audit import SecretKind, SecretReveal, SecretRotation
from app.models.site import Site
from app.models.user import AuthMethod, User

__all__ = [
    "Base",
    "AssignmentScope",
    "AuditLog",
    "AuditOutcome",
    "AuthMethod",
    "BackupSource",
    "BackupStatus",
    "Device",
    "DeviceBackup",
    "DeviceStatus",
    "DeviceTransport",
    "Organization",
    "Permission",
    "PermissionAction",
    "RefreshToken",
    "Role",
    "RoleAssignment",
    "SecretKind",
    "SecretReveal",
    "SecretRotation",
    "Site",
    "User",
]
