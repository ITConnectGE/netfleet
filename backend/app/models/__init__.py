"""SQLAlchemy ORM models — importing this module registers all tables on Base.metadata."""

from app.core.database import Base
from app.models.access_request import AccessRequest, AccessRequestGrant, AccessRequestStatus
from app.models.audit_log import AuditLog, AuditOutcome
from app.models.device import (
    BecomeMethod,
    Device,
    DeviceClass,
    DeviceStatus,
    DeviceTransport,
    OsFamily,
)
from app.models.device_backup import BackupSource, BackupStatus, DeviceBackup
from app.models.device_log_event import DeviceLogEvent, EventSeverity, EventSource
from app.models.host_metric import HostMetricSample
from app.models.organization import Organization
from app.models.refresh_token import RefreshToken
from app.models.role import AssignmentScope, Permission, PermissionAction, Role, RoleAssignment
from app.models.secret_audit import SecretKind, SecretReveal, SecretRotation
from app.models.site import Site
from app.models.tenant import Tenant
from app.models.user import AuthMethod, User
from app.models.wg_peer_secret import WgPeerSecret

__all__ = [
    "Base",
    "AccessRequest",
    "AccessRequestGrant",
    "AccessRequestStatus",
    "AssignmentScope",
    "AuditLog",
    "AuditOutcome",
    "AuthMethod",
    "BackupSource",
    "BackupStatus",
    "BecomeMethod",
    "Device",
    "DeviceBackup",
    "DeviceClass",
    "DeviceLogEvent",
    "DeviceStatus",
    "DeviceTransport",
    "EventSeverity",
    "EventSource",
    "HostMetricSample",
    "Organization",
    "OsFamily",
    "Permission",
    "PermissionAction",
    "RefreshToken",
    "Role",
    "RoleAssignment",
    "SecretKind",
    "SecretReveal",
    "SecretRotation",
    "Site",
    "Tenant",
    "User",
    "WgPeerSecret",
]
