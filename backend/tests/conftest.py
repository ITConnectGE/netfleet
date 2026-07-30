"""Shared fixtures.

The driver tests deliberately do not touch a network or a database: they
feed recorded command output through the parsers, which is where every
bug found in production so far has lived.
"""

from __future__ import annotations

import pytest

from app.drivers import ssh_transport as ssh
from app.drivers.base import DeviceCredentials
from app.drivers.linux import LinuxDriver
from helpers import ok


@pytest.fixture
def creds() -> DeviceCredentials:
    return DeviceCredentials(
        host="10.0.0.5",
        port=22,
        username="netfleet",
        transport="ssh",
        ssh_port=22,
        become_method="sudo",
    )


@pytest.fixture
def driver() -> LinuxDriver:
    return LinuxDriver()


@pytest.fixture
def fake_ssh(monkeypatch):
    """Replace the transport with canned results.

    `results(*CommandResult)` queues one batch; `sent()` returns the
    commands the driver issued, so a test can assert on the exact argv and
    on whether it escalated.
    """

    class Fake:
        def __init__(self) -> None:
            self.commands: list[ssh.Command] = []
            self._batches: list[list[ssh.CommandResult]] = []
            self._single: list[ssh.CommandResult] = []

        def results(self, *rs: ssh.CommandResult) -> None:
            self._batches.append(list(rs))

        def single(self, *rs: ssh.CommandResult) -> None:
            self._single.extend(rs)

        def sent(self) -> list[ssh.Command]:
            return self.commands

        async def _run_many(self, _creds, cmds, **_kw):
            self.commands.extend(cmds)
            got = self._batches.pop(0) if self._batches else [ok("") for _ in cmds]
            return ssh.SshBatchResult(results=got, host_key_fingerprint="SHA256:test")

        async def _run(self, _creds, argv, **kw):
            self.commands.append(ssh.Command(argv=argv, become=kw.get("become", False)))
            return self._single.pop(0) if self._single else ok("")

    fake = Fake()
    monkeypatch.setattr(ssh, "run_many", fake._run_many)
    monkeypatch.setattr(ssh, "run", fake._run)
    return fake
