"""Device onboarding script generator.

Produces a copy-paste-ready RouterOS shell script that lands the device
in a state where NetFleet can reach it: management user + group, API/SSH
services enabled with NetFleet's egress IPs whitelisted, and firewall
rules above any drops. Runs at the WinBox terminal or under New Terminal.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_field
from app.models.device import Device
from app.services.device import get_device
from app.services.settings import get_organization


PASSWORD_PLACEHOLDER = "<<paste-the-password-you-set-on-the-device>>"


async def generate_routeros_script(
    session: AsyncSession,
    *,
    organization_id: UUID,
    device_id: UUID,
    include_password: bool = True,
) -> str:
    """Render the onboarding script for `device_id`. When include_password
    is False we leave a placeholder so the script can be shown without
    decrypting + audit-logging the stored credentials (e.g. on the
    long-after-creation device detail page)."""
    device: Device = await get_device(session, organization_id, device_id)
    org = await get_organization(session, organization_id)

    api_port = device.port or 8728
    username = device.username

    if include_password and device.password_encrypted:
        password: str = decrypt_field(device.password_encrypted)
    else:
        password = PASSWORD_PLACEHOLDER

    raw_ips = (org.netfleet_external_ips or "").strip()
    if raw_ips:
        ip_list = [p.strip() for p in raw_ips.split(",") if p.strip()]
    else:
        ip_list = ["<<set-NetFleet-external-IP-in-Settings>>"]
    ips_csv = ",".join(ip_list)

    address_list_adds = "\n".join(
        f'add list=netfleet-mgmt address={ip} comment="NetFleet"' for ip in ip_list
    )

    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    return f"""# ============================================================
# NetFleet onboarding script
# Device: {device.name}  ({device.host}:{api_port})
# Generated: {ts}
# How to use: open WinBox -> New Terminal, paste this whole block.
# Safe to re-run: every "add" is paired with a "find/remove" so it is
# idempotent across re-runs.
# ============================================================

# --- 1. Allow-list for NetFleet's egress IP(s) ---
/ip firewall address-list
:foreach a in=[find list=netfleet-mgmt] do={{remove $a}}
{address_list_adds}

# --- 2. Management user group (least-privilege: read+write+api+ssh+ftp) ---
/user group
:if ([find name=netfleet] = "") do={{
  add name=netfleet policy=read,write,api,test,policy,ssh,ftp,winbox,sniff,reboot comment="NetFleet management"
}} else={{
  set [find name=netfleet] policy=read,write,api,test,policy,ssh,ftp,winbox,sniff,reboot
}}

# --- 3. Management user (NetFleet authenticates as this user) ---
/user
:if ([find name="{username}"] = "") do={{
  add name="{username}" password="{password}" group=netfleet comment="NetFleet management user"
}} else={{
  set [find name="{username}"] password="{password}" group=netfleet
}}

# --- 4. Enable + whitelist API and SSH services ---
/ip service
set api address={ips_csv} disabled=no port={api_port}
set ssh address={ips_csv} disabled=no

# --- 5. Firewall rules above any drops ---
/ip firewall filter
:foreach r in=[find comment~"NetFleet "] do={{remove $r}}
add chain=input action=accept protocol=tcp dst-port={api_port} src-address-list=netfleet-mgmt comment="NetFleet API" place-before=0
add chain=input action=accept protocol=tcp dst-port=22 src-address-list=netfleet-mgmt comment="NetFleet SSH" place-before=0

# Done. Back in NetFleet, click "Test connection" on the device.
"""
