"""Constructors for canned command results.

A module rather than conftest fixtures: these are used inline dozens of
times per test file, and `ok(PASSWD)` reads better than a fixture
parameter. Imported as a bare name — pytest puts the test directory on
sys.path for a non-package tests/ dir, so `tests.conftest` style imports
break outside a checkout that happens to have the parent on the path.
"""

from __future__ import annotations

from app.drivers import ssh_transport as ssh


def ok(stdout: str = "", stderr: str = "") -> ssh.CommandResult:
    return ssh.CommandResult(rc=0, stdout=stdout, stderr=stderr)


def fail(stderr: str = "boom", rc: int = 1) -> ssh.CommandResult:
    return ssh.CommandResult(rc=rc, stdout="", stderr=stderr)
