"""Secret-reveal + rotation tracking, and the "departing-user risk report".

Every time we expose plaintext secret material to a user we MUST call
`record_reveal()`. Every time a secret is changed (via NetFleet or detected by
the worker) we call `record_rotation()`. The risk report joins the two:
secrets a user revealed and which haven't been rotated *since* they revealed
them are flagged for immediate rotation when that user is disabled.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.secret_audit import SecretKind, SecretReveal, SecretRotation


# ---------------- record events ----------------


async def record_reveal(
    session: AsyncSession,
    *,
    organization_id: UUID,
    user_id: UUID | None,
    device_id: UUID,
    secret_kind: SecretKind,
    secret_identifier: str,
    secret_label: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    justification: str | None = None,
) -> SecretReveal:
    reveal = SecretReveal(
        organization_id=organization_id,
        user_id=user_id,
        device_id=device_id,
        secret_kind=secret_kind,
        secret_identifier=secret_identifier,
        secret_label=secret_label,
        ip_address=ip_address,
        user_agent=user_agent[:512] if user_agent else None,
        justification=justification[:1024] if justification else None,
    )
    session.add(reveal)
    await session.flush()
    return reveal


async def record_rotation(
    session: AsyncSession,
    *,
    organization_id: UUID,
    rotated_by_user_id: UUID | None,
    device_id: UUID,
    secret_kind: SecretKind,
    secret_identifier: str,
    note: str | None = None,
) -> SecretRotation:
    rotation = SecretRotation(
        organization_id=organization_id,
        rotated_by_user_id=rotated_by_user_id,
        device_id=device_id,
        secret_kind=secret_kind,
        secret_identifier=secret_identifier,
        note=note,
    )
    session.add(rotation)
    await session.flush()
    return rotation


# ---------------- risk report ----------------


@dataclass(slots=True)
class UnrotatedSecret:
    device_id: UUID
    device_name: str
    secret_kind: SecretKind
    secret_identifier: str
    secret_label: str | None
    revealed_at: datetime
    last_rotated_at: datetime | None


async def user_risk_report(
    session: AsyncSession,
    *,
    organization_id: UUID,
    user_id: UUID,
) -> list[UnrotatedSecret]:
    """All secrets this user revealed which have NOT been rotated since.

    Per (device_id, secret_kind, secret_identifier):
      * max(reveal.ts) by this user
      * max(rotation.ts) across all rotations
    Include if max_reveal > (max_rotation or epoch).
    """
    reveals_stmt = (
        select(
            SecretReveal.device_id,
            SecretReveal.secret_kind,
            SecretReveal.secret_identifier,
            func.max(SecretReveal.ts).label("last_reveal"),
            func.max(SecretReveal.secret_label).label("any_label"),
        )
        .where(
            SecretReveal.organization_id == organization_id,
            SecretReveal.user_id == user_id,
        )
        .group_by(
            SecretReveal.device_id,
            SecretReveal.secret_kind,
            SecretReveal.secret_identifier,
        )
    )
    reveals_rows = (await session.execute(reveals_stmt)).all()
    if not reveals_rows:
        return []

    rotations_stmt = (
        select(
            SecretRotation.device_id,
            SecretRotation.secret_kind,
            SecretRotation.secret_identifier,
            func.max(SecretRotation.ts).label("last_rotation"),
        )
        .where(SecretRotation.organization_id == organization_id)
        .group_by(
            SecretRotation.device_id,
            SecretRotation.secret_kind,
            SecretRotation.secret_identifier,
        )
    )
    rotations = {
        (r.device_id, r.secret_kind, r.secret_identifier): r.last_rotation
        for r in (await session.execute(rotations_stmt)).all()
    }

    # Device name lookup for the rows we care about
    device_ids = {r.device_id for r in reveals_rows}
    devices = {
        d.id: d.name
        for d in (
            await session.execute(select(Device).where(Device.id.in_(device_ids)))
        )
        .scalars()
    }

    out: list[UnrotatedSecret] = []
    for r in reveals_rows:
        key = (r.device_id, r.secret_kind, r.secret_identifier)
        last_rotation = rotations.get(key)
        if last_rotation is None or last_rotation < r.last_reveal:
            out.append(
                UnrotatedSecret(
                    device_id=r.device_id,
                    device_name=devices.get(r.device_id, "(unknown)"),
                    secret_kind=r.secret_kind,
                    secret_identifier=r.secret_identifier,
                    secret_label=r.any_label,
                    revealed_at=r.last_reveal,
                    last_rotated_at=last_rotation,
                )
            )
    # Newest revelations first
    out.sort(key=lambda x: x.revealed_at, reverse=True)
    return out
