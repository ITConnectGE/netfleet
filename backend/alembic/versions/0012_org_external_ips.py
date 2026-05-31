"""organization NetFleet external IPs (for onboarding script whitelist)

Revision ID: 0012_org_external_ips
Revises: 0011_org_sms
Create Date: 2026-05-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_org_external_ips"
down_revision: str | None = "0011_org_sms"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("netfleet_external_ips", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("organizations", "netfleet_external_ips")
