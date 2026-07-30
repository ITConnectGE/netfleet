"""Device onboarding script generator.

Produces a copy-paste-ready script that lands the device in a state where
NetFleet can reach it: management user, transport enabled with NetFleet's
egress IPs whitelisted, and firewall rules above any drops.

Two flavours, same contract — generate in NetFleet, paste on the device,
click "Test connection":

* RouterOS — runs at the WinBox terminal / New Terminal.
* Linux — runs as `sudo bash` on the target host.
"""

from __future__ import annotations

import ipaddress
import re
import shlex
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_field
from app.models.device import Device, DeviceClass
from app.services.device import get_device
from app.services.settings import get_organization
from app.services.ssh_keys import public_key_from_private_pem

PASSWORD_PLACEHOLDER = "<<paste-the-password-you-set-on-the-device>>"
PUBKEY_PLACEHOLDER = "<<no-SSH-key-on-this-device — recreate it with 'Generate SSH key'>>"

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def _comment_safe(value: str) -> str:
    """Make a value safe to drop into a `#` comment line.

    A newline would close the comment and hand the rest of the line to the
    interpreter. The device schema rejects control characters at the API
    boundary, so this only ever fires for rows created before that rule —
    but the generators must not depend on that having held."""
    return _CONTROL_CHARS.sub(" ", value)


def _routeros_quote(value: str) -> str:
    """Escape a value for use inside a double-quoted RouterOS script string.

    RouterOS is not POSIX shell — `shlex.quote` produces single quotes,
    which RouterOS does not treat as quoting at all. Backslash, double
    quote and `$` are the metacharacters that matter inside `"…"`, and a
    literal newline would end the statement."""
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("$", "\\$")
        .replace("\r", "")
        .replace("\n", "")
    )
    return _CONTROL_CHARS.sub("", escaped)


def _validated_mgmt_ips(raw: str | None) -> list[str]:
    """Parse the org's egress-IP setting into entries safe to put in a
    firewall rule. Anything unparseable is dropped rather than passed
    through — a bad entry in a generated root script is worse than a
    missing one, and the operator sees the warning the script prints when
    the list comes back empty."""
    if not raw or not raw.strip():
        return []
    out: list[str] = []
    for part in raw.split(","):
        entry = part.strip()
        if not entry:
            continue
        try:
            ipaddress.ip_network(entry, strict=False)
        except ValueError:
            continue
        out.append(entry)
    return out


async def generate_script(
    session: AsyncSession,
    *,
    organization_id: UUID,
    device_id: UUID,
    include_password: bool = True,
) -> tuple[str, str]:
    """Dispatch to the right generator for the device. Returns
    ``(script_text, file_extension)``."""
    device: Device = await get_device(session, organization_id, device_id)
    if device.device_class is DeviceClass.SERVER:
        return (
            await generate_linux_script(
                session,
                organization_id=organization_id,
                device_id=device_id,
                include_password=include_password,
            ),
            "sh",
        )
    return (
        await generate_routeros_script(
            session,
            organization_id=organization_id,
            device_id=device_id,
            include_password=include_password,
        ),
        "rsc",
    )


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
    # Both are interpolated into a RouterOS script that runs with full
    # router privileges, so they are escaped for that syntax — not shell.
    username = _routeros_quote(device.username)

    if include_password and device.password_encrypted:
        password: str = _routeros_quote(decrypt_field(device.password_encrypted))
    else:
        password = PASSWORD_PLACEHOLDER

    ip_list = _validated_mgmt_ips(org.netfleet_external_ips)
    if not ip_list:
        ip_list = ["<<set-NetFleet-external-IP-in-Settings>>"]
    ips_csv = ",".join(ip_list)

    address_list_adds = "\n".join(
        f'add list=netfleet-mgmt address={ip} comment="NetFleet"' for ip in ip_list
    )

    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    return f"""# ============================================================
# NetFleet onboarding script
# Device: {_comment_safe(device.name)}  ({_comment_safe(device.host)}:{api_port})
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


# ---------------------------------------------------------------- Linux


# The body is a plain (non-f) string with @@TOKEN@@ placeholders rather
# than an f-string: shell is dense with ${...} and awk uses braces, and
# doubling every one of them to survive f-string parsing would make the
# script unreadable.
_LINUX_SCRIPT_BODY = r'''
set -euo pipefail

# Every value below is shell-quoted by the generator, so the surrounding
# quotes are deliberately absent — adding them would break the quoting.
NETFLEET_USER=@@USER@@
NETFLEET_PUBKEY=@@PUBKEY@@
KEY_COMMENT=@@KEY_COMMENT@@
SSH_PORT=@@SSH_PORT@@
MGMT_IPS=@@MGMT_IPS@@
USE_SUDO=@@USE_SUDO@@

if [ "$(id -u)" -ne 0 ]; then
  echo "This script must run as root.  Try:  sudo bash $0" >&2
  exit 1
fi

say() { printf '\n==> %s\n' "$1"; }
warn() { printf '\n!!  %s\n' "$1" >&2; }

# --- 1. Management user ------------------------------------------------
say "Management user: $NETFLEET_USER"
if id "$NETFLEET_USER" >/dev/null 2>&1; then
  echo "    already exists - leaving it alone"
else
  useradd --create-home --shell /bin/bash \
          --comment "NetFleet management" "$NETFLEET_USER"
  # Key-only account: no password is ever set, so password logins stay
  # locked while public-key auth still works. Only ever applied to an
  # account this script just created - locking one that already existed
  # could cut off a human who uses it.
  usermod --lock "$NETFLEET_USER" >/dev/null 2>&1 || true
  echo "    created (password login locked, key auth only)"
fi

HOME_DIR="$(getent passwd "$NETFLEET_USER" | cut -d: -f6)"
# Not necessarily a group of the same name: useradd honours
# USERGROUPS_ENAB, so on some distros the primary group is 'users'.
USER_GID="$(getent passwd "$NETFLEET_USER" | cut -d: -f4)"
if [ -z "$HOME_DIR" ] || [ ! -d "$HOME_DIR" ]; then
  warn "Could not resolve a home directory for $NETFLEET_USER"
  exit 1
fi

# --- 2. Authorized key -------------------------------------------------
say "Installing NetFleet public key"
AK="$HOME_DIR/.ssh/authorized_keys"
install -d -m 700 -o "$NETFLEET_USER" -g "$USER_GID" "$HOME_DIR/.ssh"
touch "$AK"
TMP_AK="$(mktemp)"
# Drop any previous key NetFleet installed (matched on its comment), then
# append the current one - that is what makes re-running this safe.
grep -v " ${KEY_COMMENT}$" "$AK" > "$TMP_AK" || true
# head -n1 is belt and braces: the generator already guarantees a
# single-line key, and this makes sure a malformed one can never append a
# second, unintended entry to authorized_keys.
printf '%s\n' "$NETFLEET_PUBKEY" | head -n 1 >> "$TMP_AK"
install -m 600 -o "$NETFLEET_USER" -g "$USER_GID" "$TMP_AK" "$AK"
rm -f "$TMP_AK"
command -v restorecon >/dev/null 2>&1 && restorecon -R "$HOME_DIR/.ssh" >/dev/null 2>&1 || true
echo "    installed in $AK"

# --- 3. sudo -----------------------------------------------------------
if [ "$USE_SUDO" = "yes" ]; then
  say "Granting passwordless sudo"
  if ! command -v sudo >/dev/null 2>&1; then
    warn "sudo is not installed. Install it, or set this device to 'Direct root access'."
    exit 1
  fi
  SUDOERS=/etc/sudoers.d/90-netfleet
  printf '%s ALL=(ALL) NOPASSWD:ALL\n' "$NETFLEET_USER" > "$SUDOERS"
  chmod 440 "$SUDOERS"
  # Never leave a syntactically broken drop-in behind - a bad sudoers file
  # breaks sudo for every user on the box, not just this one.
  if command -v visudo >/dev/null 2>&1 && ! visudo -cf "$SUDOERS" >/dev/null; then
    rm -f "$SUDOERS"
    warn "Generated sudoers file failed validation and was removed."
    exit 1
  fi
  echo "    $SUDOERS"
else
  say "Skipping sudo (device is configured for direct root access)"
fi

# --- 4. sshd -----------------------------------------------------------
say "Checking sshd"
SSHD_CONF=/etc/ssh/sshd_config
if [ -f "$SSHD_CONF" ]; then
  if grep -Eq '^[[:space:]]*PubkeyAuthentication[[:space:]]+no' "$SSHD_CONF"; then
    warn "PubkeyAuthentication is 'no' in $SSHD_CONF - NetFleet cannot log in until that changes."
  fi
  # AllowUsers / AllowGroups are deliberately NOT edited: guessing wrong
  # here locks every admin out of the box. Report and let a human decide.
  if grep -Eq '^[[:space:]]*(AllowUsers|AllowGroups|DenyUsers)' "$SSHD_CONF"; then
    warn "$SSHD_CONF restricts logins (AllowUsers/AllowGroups/DenyUsers). Add '$NETFLEET_USER' there by hand."
  fi
fi
systemctl is-enabled sshd >/dev/null 2>&1 || systemctl is-enabled ssh >/dev/null 2>&1 || \
  warn "sshd does not look enabled at boot."

# --- 5. Firewall -------------------------------------------------------
say "Allowing NetFleet's IP(s) to reach port $SSH_PORT"
if [ -z "$MGMT_IPS" ]; then
  warn "No NetFleet egress IP is configured. Set it in NetFleet under Settings, then regenerate this script."
fi

fw_ufw() {
  command -v ufw >/dev/null 2>&1 || return 1
  ufw status 2>/dev/null | head -1 | grep -q "Status: active" || return 1
  for ip in $MGMT_IPS; do
    ufw allow from "$ip" to any port "$SSH_PORT" proto tcp comment "NetFleet" >/dev/null
    echo "    ufw: allowed $ip"
  done
  return 0
}

fw_firewalld() {
  command -v firewall-cmd >/dev/null 2>&1 || return 1
  firewall-cmd --state >/dev/null 2>&1 || return 1
  for ip in $MGMT_IPS; do
    case "$ip" in *:*) fam=ipv6 ;; *) fam=ipv4 ;; esac
    firewall-cmd --permanent \
      --add-rich-rule="rule family=\"$fam\" source address=\"$ip\" port port=\"$SSH_PORT\" protocol=\"tcp\" accept" >/dev/null
    echo "    firewalld: allowed $ip"
  done
  firewall-cmd --reload >/dev/null
  return 0
}

fw_nft() {
  command -v nft >/dev/null 2>&1 || return 1
  for tbl in "inet filter" "ip filter"; do
    nft list chain $tbl input >/dev/null 2>&1 || continue
    # Purge our previous rules by handle so re-runs do not stack up.
    for h in $(nft -a list chain $tbl input | awk '/comment "netfleet"/ {print $NF}'); do
      nft delete rule $tbl input handle "$h" 2>/dev/null || true
    done
    for ip in $MGMT_IPS; do
      case "$ip" in *:*) sa=ip6 ;; *) sa=ip ;; esac
      nft insert rule $tbl input $sa saddr "$ip" tcp dport "$SSH_PORT" accept comment "netfleet"
      echo "    nftables ($tbl): allowed $ip"
    done
    return 0
  done
  return 1
}

fw_iptables() {
  command -v iptables >/dev/null 2>&1 || return 1
  for ip in $MGMT_IPS; do
    case "$ip" in *:*) continue ;; esac
    iptables -C INPUT -s "$ip" -p tcp --dport "$SSH_PORT" -j ACCEPT 2>/dev/null || \
      iptables -I INPUT 1 -s "$ip" -p tcp --dport "$SSH_PORT" -j ACCEPT
    echo "    iptables: allowed $ip"
  done
  warn "iptables rules are not persistent across reboot unless you save them (iptables-save)."
  return 0
}

if [ -n "$MGMT_IPS" ]; then
  fw_ufw || fw_firewalld || fw_nft || fw_iptables || \
    warn "No managed firewall found. If something upstream filters port $SSH_PORT, open it manually."
fi

# --- 6. Host key fingerprints -----------------------------------------
say "SSH host key fingerprints (NetFleet pins one of these on first connect)"
for f in /etc/ssh/ssh_host_*_key.pub; do
  [ -e "$f" ] || continue
  ssh-keygen -lf "$f" 2>/dev/null | sed 's/^/    /'
done

say "Done."
echo "    Back in NetFleet, click \"Test connection\" on this device."
'''


async def generate_linux_script(
    session: AsyncSession,
    *,
    organization_id: UUID,
    device_id: UUID,
    include_password: bool = True,
) -> str:
    """Render the Linux onboarding script for `device_id`.

    Mirrors the RouterOS flow: management user, NetFleet's egress IPs
    allowed to the SSH port, everything idempotent so re-running after a
    config drift is safe. `include_password` exists for signature parity
    with the RouterOS generator — key-based onboarding never emits a
    secret, so it changes nothing here.
    """
    device: Device = await get_device(session, organization_id, device_id)
    org = await get_organization(session, organization_id)

    # Keyed on the device UUID, never on the display name: this string is
    # appended to the public key and that whole line is written into a
    # remote authorized_keys. A name-derived comment lets anyone who can
    # rename a device append a second key of their choosing — which shell
    # quoting alone would not prevent, since the injection is a newline
    # inside an already-quoted value.
    key_comment = f"netfleet-{device.id}"
    if device.ssh_private_key_encrypted:
        pubkey = public_key_from_private_pem(
            decrypt_field(device.ssh_private_key_encrypted), comment=key_comment
        )
    else:
        pubkey = PUBKEY_PLACEHOLDER

    ip_list = _validated_mgmt_ips(org.netfleet_external_ips)
    ssh_port = device.ssh_port or 22
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    # Comment lines are still interpolation sites: a newline would end the
    # comment and turn the rest into code. The schema rejects control
    # characters on the way in; this is the second line of defence for rows
    # that predate that rule.
    safe_name = _comment_safe(device.name)
    safe_host = _comment_safe(device.host)
    safe_user = _comment_safe(device.username)

    header = f"""#!/usr/bin/env bash
# ============================================================
# NetFleet onboarding script
# Host: {safe_name}  ({safe_host}:{ssh_port})
# Generated: {ts}
#
# How to use — copy this file onto the server and run:
#     sudo bash netfleet-onboarding.sh
#
# What it does:
#   1. creates the '{safe_user}' management user (no password — key only)
#   2. installs NetFleet's public key in its authorized_keys
#   3. grants it passwordless sudo via /etc/sudoers.d/90-netfleet
#   4. allows NetFleet's egress IP(s) to reach TCP {ssh_port}
#   5. prints the host key fingerprints
#
# Safe to re-run: every step is idempotent.
# It never edits AllowUsers/AllowGroups and never enables an inactive
# firewall — both are reliable ways to lock yourself out of a server.
# ============================================================
"""

    # shlex.quote on every substitution. The template deliberately omits the
    # surrounding quotes so this is the single place quoting happens.
    body = (
        _LINUX_SCRIPT_BODY.replace("@@USER@@", shlex.quote(device.username))
        .replace("@@PUBKEY@@", shlex.quote(pubkey))
        .replace("@@KEY_COMMENT@@", shlex.quote(key_comment))
        .replace("@@SSH_PORT@@", shlex.quote(str(ssh_port)))
        .replace("@@MGMT_IPS@@", shlex.quote(" ".join(ip_list)))
        .replace(
            "@@USE_SUDO@@",
            shlex.quote("yes" if device.become_method.value == "sudo" else "no"),
        )
    )
    return header + body
