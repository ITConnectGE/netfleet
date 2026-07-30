"""SSH command transport for driver implementations.

Kept separate from `drivers/linux.py` so the connection/auth/escalation
mechanics can be tested on their own, and so a future vendor that also
speaks only SSH can reuse it.

Design notes:

* **argv, never a shell string.** Callers pass `["ip", "-j", "addr"]`; the
  join through `shlex.quote` happens here. Nothing built from device data
  ever reaches a shell unquoted.
* **One connection, many commands.** `run_many` opens a single session and
  runs the whole batch, because a driver call like `system_info` needs half
  a dozen small reads and paying TCP + auth for each one is the difference
  between a snappy page and a slow one.
* **Blocking paramiko inside `asyncio.to_thread`**, matching the pattern the
  MikroTik driver already uses for SFTP.
* **Trust on first use.** The caller supplies the pinned fingerprint (or
  None on the very first connect) and gets the observed one back to store.
"""

from __future__ import annotations

import asyncio
import select
import shlex
import time
from dataclasses import dataclass, field
from io import StringIO
from typing import TYPE_CHECKING, Any

import structlog

from app.drivers.base import DeviceCredentials
from app.services.ssh_keys import fingerprint_from_key_bytes

if TYPE_CHECKING:  # pragma: no cover - import cost only paid at runtime
    import paramiko

log = structlog.get_logger(__name__)

DEFAULT_TIMEOUT = 30.0
DEFAULT_CONNECT_TIMEOUT = 15.0
# A runaway `cat /dev/urandom` must not be able to exhaust API memory.
DEFAULT_MAX_OUTPUT = 1_048_576


class SshError(Exception):
    """Base for every failure this module raises."""


class SshAuthError(SshError):
    pass


class SshConnectError(SshError):
    pass


class SshTimeout(SshError):
    pass


class HostKeyMismatch(SshError):
    """The host presented a different key than the one pinned for it.

    Treated as fatal rather than a prompt: on an unattended management
    plane there is nobody to eyeball the new fingerprint, and silently
    accepting it defeats the point of pinning.
    """


class BecomeUnavailable(SshError):
    """Privilege escalation was requested but cannot be performed."""


@dataclass(slots=True)
class Command:
    argv: list[str]
    become: bool = False
    # Fed to the command on stdin. Used for things like `chpasswd`; the
    # sudo password is handled separately and never goes through here.
    stdin: str | None = None
    timeout: float = DEFAULT_TIMEOUT


@dataclass(slots=True)
class CommandResult:
    rc: int
    stdout: str
    stderr: str
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return self.rc == 0

    def check(self, what: str) -> CommandResult:
        """Raise unless the command succeeded. `what` names the operation
        for the error message the operator will actually see."""
        if not self.ok:
            detail = (self.stderr or self.stdout).strip().splitlines()
            msg = detail[0] if detail else f"exit status {self.rc}"
            raise SshError(f"{what} failed: {msg}")
        return self


@dataclass(slots=True)
class SshBatchResult:
    results: list[CommandResult]
    host_key_fingerprint: str
    fields: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------- internals


def _load_private_key(pem: str, passphrase: str | None) -> paramiko.PKey:
    import paramiko

    # NetFleet generates Ed25519, but an operator may paste in an existing
    # key of any type, so try each until one parses.
    candidates = (
        paramiko.Ed25519Key,
        paramiko.ECDSAKey,
        paramiko.RSAKey,
        paramiko.DSSKey,
    )
    last_error: Exception | None = None
    for cls in candidates:
        try:
            return cls.from_private_key(StringIO(pem), password=passphrase)
        except Exception as e:  # noqa: BLE001 - any parse failure means "try the next type"
            last_error = e
    raise SshAuthError(f"could not parse the stored SSH private key: {last_error}")


def _make_policy(expected: str | None) -> Any:
    """Build a paramiko host-key policy implementing trust-on-first-use.

    Constructed inside a function because paramiko is imported lazily —
    the class cannot be declared at module scope without paying that
    import on every API start.
    """
    import paramiko

    class _Policy(paramiko.MissingHostKeyPolicy):
        def __init__(self) -> None:
            self.observed: str | None = None

        def missing_host_key(
            self, client: Any, hostname: str, key: paramiko.PKey
        ) -> None:
            fp = fingerprint_from_key_bytes(key.asbytes())
            self.observed = fp
            if expected and fp != expected:
                raise HostKeyMismatch(
                    f"host key for {hostname} changed: pinned {expected}, got {fp}. "
                    "If this host was legitimately rebuilt, clear the pinned key on "
                    "the device and reconnect."
                )

    return _Policy()


def _connect(creds: DeviceCredentials) -> tuple[paramiko.SSHClient, str]:
    import paramiko

    client = paramiko.SSHClient()
    policy = _make_policy(creds.host_key_fingerprint)
    client.set_missing_host_key_policy(policy)

    kwargs: dict[str, Any] = {
        "hostname": creds.host,
        "port": creds.ssh_port or 22,
        "username": creds.username,
        "timeout": DEFAULT_CONNECT_TIMEOUT,
        "banner_timeout": DEFAULT_CONNECT_TIMEOUT,
        "auth_timeout": DEFAULT_CONNECT_TIMEOUT,
        # The API host's own ~/.ssh must never influence which key we
        # present — credentials come from the device record, full stop.
        "look_for_keys": False,
        "allow_agent": False,
    }
    if creds.ssh_private_key:
        kwargs["pkey"] = _load_private_key(creds.ssh_private_key, creds.ssh_key_passphrase)
    elif creds.password:
        kwargs["password"] = creds.password
    else:
        raise SshAuthError("device has neither an SSH key nor a password configured")

    try:
        client.connect(**kwargs)
    except HostKeyMismatch:
        client.close()
        raise
    except paramiko.AuthenticationException as e:
        client.close()
        raise SshAuthError(
            f"authentication as '{creds.username}' was rejected by {creds.host}. "
            "Has the onboarding script been run on this host?"
        ) from e
    except Exception as e:  # noqa: BLE001 - socket errors, SSH protocol errors, DNS
        client.close()
        raise SshConnectError(f"could not connect to {creds.host}:{creds.ssh_port} — {e}") from e

    fingerprint = policy.observed or creds.host_key_fingerprint or ""
    return client, fingerprint


def _build_command(cmd: Command, creds: DeviceCredentials) -> str:
    quoted = shlex.join(cmd.argv)
    if not cmd.become:
        return quoted
    if creds.become_method != "sudo":
        raise BecomeUnavailable(
            "this operation needs elevated privileges, but the device is not "
            "configured to use sudo"
        )
    if creds.become_password:
        # -S reads the password from stdin; -p '' suppresses the prompt so
        # it cannot end up mixed into the command's stdout.
        return f"sudo -S -p '' -- {quoted}"
    # NOPASSWD path — what the onboarding script sets up. -n makes sudo
    # fail fast instead of hanging on a prompt nobody can answer.
    return f"sudo -n -- {quoted}"


def _exec_one(
    client: paramiko.SSHClient,
    cmd: Command,
    creds: DeviceCredentials,
    max_output: int,
) -> CommandResult:
    transport = client.get_transport()
    if transport is None:  # pragma: no cover - only after an abrupt disconnect
        raise SshConnectError("SSH transport closed unexpectedly")

    chan = transport.open_session()
    try:
        chan.settimeout(cmd.timeout)
        chan.exec_command(_build_command(cmd, creds))

        if cmd.become and creds.become_password:
            chan.sendall(f"{creds.become_password}\n".encode())
        if cmd.stdin:
            chan.sendall(cmd.stdin.encode())
        chan.shutdown_write()

        out = bytearray()
        err = bytearray()
        truncated = False
        deadline = time.monotonic() + cmd.timeout

        # Drain both streams together. Reading stdout to completion first
        # deadlocks as soon as a command writes more to stderr than the
        # channel window holds.
        while True:
            if time.monotonic() > deadline:
                raise SshTimeout(
                    f"command timed out after {cmd.timeout:g}s: {' '.join(cmd.argv[:3])}"
                )

            select.select([chan], [], [], 0.1)

            while chan.recv_ready():
                out += chan.recv(65536)
            while chan.recv_stderr_ready():
                err += chan.recv_stderr(65536)

            if len(out) > max_output:
                del out[max_output:]
                truncated = True
            if len(err) > max_output:
                del err[max_output:]
                truncated = True
            if truncated:
                break

            if chan.exit_status_ready() and not chan.recv_ready() and not chan.recv_stderr_ready():
                break

        rc = chan.recv_exit_status()
        return CommandResult(
            rc=rc,
            stdout=out.decode("utf-8", errors="replace"),
            stderr=err.decode("utf-8", errors="replace"),
            truncated=truncated,
        )
    finally:
        chan.close()


def _run_many_sync(
    creds: DeviceCredentials,
    commands: list[Command],
    max_output: int,
) -> SshBatchResult:
    client, fingerprint = _connect(creds)
    try:
        results = [_exec_one(client, c, creds, max_output) for c in commands]
    finally:
        client.close()
    return SshBatchResult(results=results, host_key_fingerprint=fingerprint)


# ------------------------------------------------------------------- public


async def run_many(
    creds: DeviceCredentials,
    commands: list[Command],
    *,
    max_output: int = DEFAULT_MAX_OUTPUT,
) -> SshBatchResult:
    """Run `commands` in order over a single SSH connection."""
    return await asyncio.to_thread(_run_many_sync, creds, commands, max_output)


async def run(
    creds: DeviceCredentials,
    argv: list[str],
    *,
    become: bool = False,
    stdin: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    max_output: int = DEFAULT_MAX_OUTPUT,
) -> CommandResult:
    """Run a single command. Prefer `run_many` when issuing several."""
    batch = await run_many(
        creds,
        [Command(argv=argv, become=become, stdin=stdin, timeout=timeout)],
        max_output=max_output,
    )
    return batch.results[0]


async def probe(creds: DeviceCredentials) -> SshBatchResult:
    """Cheapest possible round-trip: confirms auth works and returns the
    host key fingerprint so the caller can pin it."""
    return await run_many(creds, [Command(argv=["true"], timeout=10.0)])
