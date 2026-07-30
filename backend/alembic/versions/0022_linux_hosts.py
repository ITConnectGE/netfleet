"""Linux server support — device_class, SSH key auth, sudo, host-key pin

Revision ID: 0022_linux_hosts
Revises: 0021_host_metric_samples
Create Date: 2026-07-30

Phase 12 / Stage L1. The only migration that touches `devices` for the
whole Linux phase — everything after this builds on these columns.

`device_class` splits the fleet into network gear and servers so the UI
can route them to different pages while they share one table, one RBAC
scope tree and one audit log.

`os_family` is a plain string rather than a PG enum on purpose: it is
*discovered* data, and every new distro we learn to talk to would
otherwise cost a migration. Known values live in `models.device.OsFamily`
and are enforced Python-side. `become_method` is a genuinely closed set
(none | sudo), so it gets a real enum.

`ssh_host_key_fingerprint` implements trust-on-first-use: the first
successful connection pins the host key, and a later mismatch fails the
connection instead of silently accepting a new key.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0022_linux_hosts"
down_revision: str | None = "0021_host_metric_samples"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    device_class_enum = postgresql.ENUM("network", "server", name="device_class")
    device_class_enum.create(op.get_bind(), checkfirst=True)

    become_method_enum = postgresql.ENUM("none", "sudo", name="device_become_method")
    become_method_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "devices",
        sa.Column(
            "device_class",
            postgresql.ENUM("network", "server", name="device_class", create_type=False),
            nullable=False,
            server_default="network",
        ),
    )
    op.create_index("ix_devices_device_class", "devices", ["device_class"])

    op.add_column("devices", sa.Column("os_family", sa.String(length=32), nullable=True))
    op.add_column("devices", sa.Column("os_version", sa.String(length=64), nullable=True))
    op.add_column("devices", sa.Column("ssh_private_key_encrypted", sa.Text(), nullable=True))
    op.add_column(
        "devices",
        sa.Column("ssh_key_passphrase_encrypted", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "devices",
        sa.Column(
            "become_method",
            postgresql.ENUM("none", "sudo", name="device_become_method", create_type=False),
            nullable=False,
            server_default="none",
        ),
    )
    op.add_column(
        "devices",
        sa.Column("become_password_encrypted", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "devices",
        sa.Column("ssh_host_key_fingerprint", sa.String(length=128), nullable=True),
    )

    # Defaults exist only to backfill the existing rows; new rows get their
    # value from the ORM, same as every other column on this table.
    op.alter_column("devices", "device_class", server_default=None)
    op.alter_column("devices", "become_method", server_default=None)


def downgrade() -> None:
    op.drop_column("devices", "ssh_host_key_fingerprint")
    op.drop_column("devices", "become_password_encrypted")
    op.drop_column("devices", "become_method")
    op.drop_column("devices", "ssh_key_passphrase_encrypted")
    op.drop_column("devices", "ssh_private_key_encrypted")
    op.drop_column("devices", "os_version")
    op.drop_column("devices", "os_family")
    op.drop_index("ix_devices_device_class", table_name="devices")
    op.drop_column("devices", "device_class")

    postgresql.ENUM(name="device_become_method").drop(op.get_bind(), checkfirst=False)
    postgresql.ENUM(name="device_class").drop(op.get_bind(), checkfirst=False)
