"""site latitude + longitude for the fleet map

Revision ID: 0013_site_geolocation
Revises: 0012_org_external_ips
Create Date: 2026-05-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_site_geolocation"
down_revision: str | None = "0012_org_external_ips"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # double precision — WGS84 fits comfortably in float64 and we want
    # sub-metre precision for marker placement.
    op.add_column("sites", sa.Column("latitude", sa.Float(precision=53), nullable=True))
    op.add_column("sites", sa.Column("longitude", sa.Float(precision=53), nullable=True))


def downgrade() -> None:
    op.drop_column("sites", "longitude")
    op.drop_column("sites", "latitude")
