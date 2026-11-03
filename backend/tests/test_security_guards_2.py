"""Regression tests for the second batch of 2026-11 audit fixes:
RouterOS SFTP host-key pinning, API-SSL, OIDC linking/provisioning, and
SMTP/SMS secrets surviving a server change."""

from __future__ import annotations

import sys
import types
import uuid
from types import SimpleNamespace

import pytest

from app.drivers import mikrotik
from app.drivers.ssh_transport import HostKeyMismatch
from app.services import backups as backup_svc
from app.services import oidc as oidc_svc
from app.services import settings as settings_svc
from app.services import sms as sms_svc
from app.services.ssh_keys import fingerprint_from_key_bytes

# ---------------- SFTP host key: trust on first use, then pin ----------------


class _FakeKey:
    def __init__(self, blob: bytes) -> None:
        self._blob = blob

    def asbytes(self) -> bytes:
        return self._blob


def _fake_paramiko(monkeypatch, server_key: bytes):
    """A paramiko stand-in whose SSHClient presents `server_key`."""
    import paramiko

    class _Client:
        def set_missing_host_key_policy(self, policy):
            self.policy = policy

        def connect(self, hostname, **_kw):
            self.policy.missing_host_key(self, hostname, _FakeKey(server_key))

        def open_sftp(self):
            return SimpleNamespace(close=lambda: None)

        def close(self):
            return None

    monkeypatch.setattr(paramiko, "SSHClient", _Client)


def _session(pin):
    with mikrotik._sftp_session("r1", 22, "admin", "pw", pin):
        pass


def test_sftp_pins_on_first_use(monkeypatch):
    _fake_paramiko(monkeypatch, b"key-A")
    pin = mikrotik._HostKeyPin(None)
    _session(pin)
    assert pin.observed == fingerprint_from_key_bytes(b"key-A")


def test_sftp_refuses_changed_key_within_one_operation(monkeypatch):
    _fake_paramiko(monkeypatch, b"key-A")
    pin = mikrotik._HostKeyPin(None)
    _session(pin)
    _fake_paramiko(monkeypatch, b"key-B")  # an impostor answers the next session
    with pytest.raises(HostKeyMismatch):
        _session(pin)


def test_sftp_refuses_key_that_differs_from_stored_pin(monkeypatch):
    _fake_paramiko(monkeypatch, b"key-B")
    with pytest.raises(HostKeyMismatch):
        _session(mikrotik._HostKeyPin(fingerprint_from_key_bytes(b"key-A")))


def test_sftp_accepts_pinned_key(monkeypatch):
    _fake_paramiko(monkeypatch, b"key-A")
    pin = mikrotik._HostKeyPin(fingerprint_from_key_bytes(b"key-A"))
    _session(pin)
    assert pin.observed is None  # nothing new to persist


def test_backup_service_persists_first_pin_only():
    dev = SimpleNamespace(ssh_host_key_fingerprint=None)
    backup_svc.remember_host_key(dev, "SHA256:aaa")
    assert dev.ssh_host_key_fingerprint == "SHA256:aaa"
    backup_svc.remember_host_key(dev, "SHA256:bbb")
    assert dev.ssh_host_key_fingerprint == "SHA256:aaa"


# ---------------- RouterOS API-SSL ----------------


def _capture_connect(monkeypatch):
    seen: dict = {}

    class _Conn:
        def path(self, *_a):
            return lambda *_x, **_y: []

        def close(self):
            return None

    def fake_connect(**kw):
        seen.update(kw)
        return _Conn()

    mod = types.ModuleType("librouteros")
    mod.connect = fake_connect
    monkeypatch.setitem(sys.modules, "librouteros", mod)
    return seen


def _creds(port: int, verify: bool = True):
    return SimpleNamespace(
        host="r1.example", port=port, username="admin", password="pw", verify_tls=verify
    )


def test_api_ssl_port_wraps_in_tls(monkeypatch):
    seen = _capture_connect(monkeypatch)
    mikrotik.MikrotikDriver._call_sync(_creds(8729), "/system/identity/set", {"name": "x"})
    assert callable(seen.get("ssl_wrapper"))


def test_plain_api_port_has_no_tls(monkeypatch):
    seen = _capture_connect(monkeypatch)
    mikrotik.MikrotikDriver._call_sync(_creds(8728), "/system/identity/set", {"name": "x"})
    assert "ssl_wrapper" not in seen


def test_tls_context_honours_verify_flag():
    import ssl

    sock = SimpleNamespace()
    for verify, mode in ((True, ssl.CERT_REQUIRED), (False, ssl.CERT_NONE)):
        wrap = mikrotik._tls_context(verify, "r1.example")
        ctx = wrap.__closure__[0].cell_contents
        assert ctx.verify_mode == mode
        assert ctx.check_hostname is verify
    del sock


# ---------------- OIDC: linking and auto-provisioning ----------------


def _org(tenant: str | None):
    return SimpleNamespace(id=uuid.uuid4(), microsoft_oidc_tenant_id=tenant)


@pytest.mark.parametrize(
    "claims, provider, tenant, expected",
    [
        ({"email_verified": True}, "google", None, True),
        ({"email_verified": False}, "google", None, False),
        ({}, "google", None, False),
        ({"tid": "t-1"}, "microsoft", "t-1", True),
        ({"tid": "t-2"}, "microsoft", "t-1", False),
        ({"tid": "t-1"}, "microsoft", "common", False),
        ({"tid": "t-1"}, "microsoft", "", False),
        ({}, "microsoft", "contoso.onmicrosoft.com", True),
    ],
)
def test_email_is_vouched(claims, provider, tenant, expected):
    assert oidc_svc._email_is_vouched(claims, provider, _org(tenant)) is expected


class _OidcSession:
    """Answers: lookup by sub, lookup by email, domain count."""

    def __init__(self, *, by_sub=None, by_email=None, domain_count=0):
        self.by_sub, self.by_email, self.domain_count = by_sub, by_email, domain_count
        self.added = []
        self._calls = 0

    async def execute(self, stmt):
        self._calls += 1
        text = str(stmt)
        if "count(" in text:
            value = self.domain_count
        elif "WHERE users.oidc_sub" in text:
            value = self.by_sub
        else:
            value = self.by_email
        return SimpleNamespace(scalar_one_or_none=lambda: value, scalar_one=lambda: value)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None


async def _upsert(monkeypatch, session, claims, provider="google", tenant=None):
    org = _org(tenant)

    async def load_org(_s):
        return org

    monkeypatch.setattr(oidc_svc, "_load_org", load_org)
    return await oidc_svc.upsert_user_from_claims(session, claims=claims, provider=provider)


async def test_unverified_email_cannot_take_over_existing_account(monkeypatch):
    admin = SimpleNamespace(email="boss@itconnect.ge", is_admin=True, oidc_sub=None)
    s = _OidcSession(by_email=admin)
    with pytest.raises(oidc_svc.OidcError, match="did not confirm"):
        await _upsert(monkeypatch, s, {"sub": "x", "email": "boss@itconnect.ge"})
    assert admin.oidc_sub is None


async def test_verified_email_links_existing_account(monkeypatch):
    user = SimpleNamespace(
        email="a@itconnect.ge", oidc_sub=None, oidc_provider=None, auth_method=None,
        display_name="A", last_login_at=None,
    )
    s = _OidcSession(by_email=user)
    got = await _upsert(
        monkeypatch, s, {"sub": "g-1", "email": "a@itconnect.ge", "email_verified": True}
    )
    assert got is user and user.oidc_sub == "g-1"


async def test_random_google_account_cannot_self_provision(monkeypatch):
    s = _OidcSession(domain_count=0)
    with pytest.raises(oidc_svc.OidcError, match="not allowed"):
        await _upsert(
            monkeypatch, s, {"sub": "g-2", "email": "x@gmail.com", "email_verified": True}
        )
    assert not s.added


async def test_workspace_account_of_known_domain_is_provisioned(monkeypatch):
    s = _OidcSession(domain_count=3)
    got = await _upsert(
        monkeypatch,
        s,
        {"sub": "g-3", "email": "new@itconnect.ge", "email_verified": True, "hd": "itconnect.ge"},
    )
    assert s.added == [got] and got.is_admin is False


# ---------------- SMTP / SMS secrets don't follow a server change ----------------


def _org_settings(**kw):
    return SimpleNamespace(**kw)


async def test_smtp_host_change_drops_stored_password(monkeypatch):
    org = _org_settings(smtp_host="mail.itconnect.ge", smtp_password_encrypted="enc")

    async def get_org(_s, _id):
        return org

    monkeypatch.setattr(settings_svc, "get_organization", get_org)
    payload = settings_svc.SmtpSettingsUpdate(smtp_host="evil.example")
    await settings_svc.update_smtp(SimpleNamespace(flush=_noop), uuid.uuid4(), payload)
    assert org.smtp_password_encrypted is None


async def test_smtp_same_host_keeps_password(monkeypatch):
    org = _org_settings(smtp_host="mail.itconnect.ge", smtp_password_encrypted="enc")

    async def get_org(_s, _id):
        return org

    monkeypatch.setattr(settings_svc, "get_organization", get_org)
    payload = settings_svc.SmtpSettingsUpdate(smtp_host="MAIL.itconnect.ge", smtp_port=587)
    await settings_svc.update_smtp(SimpleNamespace(flush=_noop), uuid.uuid4(), payload)
    assert org.smtp_password_encrypted == "enc"


@pytest.mark.parametrize(
    "new_url, kept",
    [
        ("https://sms.provider.ge/send?key={key}&to={phone}", True),
        ("https://evil.example/x?key={key}", False),
    ],
)
async def test_sms_url_host_change_drops_key(monkeypatch, new_url, kept):
    org = _org_settings(
        sms_api_url="https://sms.provider.ge/api?key={key}", sms_api_key_encrypted="enc"
    )

    async def get_org(_s, _id):
        return org

    monkeypatch.setattr(sms_svc, "get_org", get_org)
    payload = sms_svc.SmsSettingsUpdate(sms_api_url=new_url)
    await sms_svc.update_sms(SimpleNamespace(flush=_noop), uuid.uuid4(), payload)
    assert (org.sms_api_key_encrypted == "enc") is kept


async def _noop():
    return None
