"""RBAC is enforced per device, and checks carry the device/site/tenant scope.

Before 2026-11 most device reads depended on get_current_user alone — any
logged-in user, with no role at all, could read every device (crontabs as
root, SNMP communities, PPP secrets lists) — and no check passed a scope,
so tenant/site/device-scoped roles never matched anything.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi.routing import APIRoute

from app.api import dependencies as deps
from app.main import app
from app.services import rbac

# Endpoints under a {device_id} that are deliberately login-only, by
# endpoint function name. Keep this list short and justified.
_LOGIN_ONLY_DEVICE_ENDPOINTS = {
    # Lists who has access to the device (names/emails) for the
    # access-request flow; returns no device data.
    "device_access",
}


def _api_routes(routes):
    """Every APIRoute, including those inside included routers (newer
    FastAPI wraps them lazily instead of flattening into app.routes)."""
    for r in routes:
        if isinstance(r, APIRoute):
            yield r
        inner = getattr(r, "original_router", None)
        if inner is not None:
            yield from _api_routes(inner.routes)


def test_route_walk_finds_device_routes():
    # Guards the guard: an empty walk would make the next test vacuous.
    assert sum("{device_id}" in r.path for r in _api_routes(app.routes)) > 50


def test_no_device_route_is_login_only():
    offenders = []
    for route in _api_routes(app.routes):
        if "{device_id}" not in route.path:
            continue
        if route.endpoint.__name__ in _LOGIN_ONLY_DEVICE_ENDPOINTS:
            continue
        calls = [d.call for d in route.dependant.dependencies]
        if deps.get_current_user in calls:
            offenders.append(f"{sorted(route.methods)} {route.path} ({route.endpoint.__name__})")
    listing = "\n".join(offenders)
    assert not offenders, f"device routes guarded by login only:\n{listing}"


@pytest.mark.parametrize(
    "params, expected",
    [
        ({"device_id": "D"}, {"device_id": "D", "site_id": None, "tenant_id": None}),
        ({"site_id": "S"}, {"device_id": None, "site_id": "S", "tenant_id": None}),
        ({"tenant_id": "T"}, {"device_id": None, "site_id": None, "tenant_id": "T"}),
        ({}, {"device_id": None, "site_id": None, "tenant_id": None}),
    ],
)
async def test_require_permission_scopes_to_path(monkeypatch, params, expected):
    ids = {k: uuid.uuid4() for k in ("D", "S", "T")}
    path_params = {k: str(ids[v]) for k, v in params.items()}
    seen = {}

    async def fake_require(_session, _user, section, action, **kw):
        seen.update(kw, section=section, action=action)

    monkeypatch.setattr(deps.rbac, "require", fake_require)
    dep = deps.require_permission("system.info", "read")
    await dep(SimpleNamespace(path_params=path_params), SimpleNamespace(), None)
    want = {k: (ids[v] if v else None) for k, v in expected.items()}
    assert {k: seen[k] for k in want} == want
    assert seen["section"] == "system.info"


async def test_require_permission_denial_is_403(monkeypatch):
    async def deny(*_a, **_kw):
        raise PermissionError("denied: system.info:read")

    monkeypatch.setattr(deps.rbac, "require", deny)
    dep = deps.require_permission("system.info", "read")
    with pytest.raises(deps.HTTPException) as e:
        await dep(SimpleNamespace(path_params={}), SimpleNamespace(), None)
    assert e.value.status_code == 403


def test_path_uuid_ignores_garbage():
    req = SimpleNamespace(path_params={"device_id": "not-a-uuid"})
    assert deps._path_uuid(req, "device_id") is None
    assert deps._path_uuid(req, "site_id") is None


def test_visibility_follows_assignment_scopes():
    v = rbac.Visibility()
    t, s, d = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    v.tenant_ids.add(t)
    v.site_ids.add(s)
    v.device_ids.add(d)
    other_site, other_tenant = uuid.uuid4(), uuid.uuid4()
    assert v.device(uuid.uuid4(), other_site, t)  # under the tenant
    assert v.device(uuid.uuid4(), s, other_tenant)  # on the site
    assert v.device(d, other_site, other_tenant)  # the device itself
    assert not v.device(uuid.uuid4(), other_site, other_tenant)
