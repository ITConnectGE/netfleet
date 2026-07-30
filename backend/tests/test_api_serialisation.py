"""Driver dataclass -> API response model.

This is the layer that produced a 500 on three endpoints at once: they
built responses with `**vars(obj)`, and every driver dataclass is declared
`slots=True`, so instances have no `__dict__`. The driver tests all passed
because they stopped one layer earlier.
"""

from __future__ import annotations

import pytest

from app.api.v1.router_system import _fields
from app.drivers import base
from app.schemas import router_system as schemas

# Each pair is a dataclass the driver returns and the model the API builds
# from it, plus fields the public shape deliberately omits.
PAIRS = [
    (base.InterfaceConfig(name="eth0"), schemas.InterfaceConfigPublic, {"raw"}),
    (base.ProcessInfo(pid=1), schemas.ProcessPublic, set()),
    (
        base.ScheduledJob(source="timer", schedule="daily", command="x"),
        schemas.ScheduledJobPublic,
        set(),
    ),
    (
        base.DiskUsage(filesystem="/dev/vda1", mount_point="/"),
        schemas.DiskUsagePublic,
        {"raw"},
    ),
    (
        base.DirEntryUsage(path="/var/log", name="log", size_bytes=1),
        schemas.DirEntryUsagePublic,
        set(),
    ),
]


@pytest.mark.parametrize("obj,model,drop", PAIRS, ids=lambda p: getattr(p, "__name__", ""))
def test_dataclass_builds_its_response_model(obj, model, drop):
    """The exact call the endpoints make. Would have caught the vars() bug."""
    built = model(**_fields(obj, drop=drop))
    assert built is not None


@pytest.mark.parametrize("obj,model,drop", PAIRS, ids=lambda p: getattr(p, "__name__", ""))
def test_every_schema_field_exists_on_the_dataclass(obj, model, drop):
    """Stops the two drifting apart: a schema field with no source would
    otherwise only fail when a request happens to exercise it."""
    available = set(_fields(obj, drop=drop))
    required = {
        name for name, f in model.model_fields.items() if f.is_required()
    }
    assert required <= available, f"{model.__name__} needs {required - available}"


def test_slots_dataclasses_have_no_dict():
    """Guards the assumption the helper exists for — if a dataclass ever
    loses `slots=True`, `_fields` still works, but the reverse does not."""
    with pytest.raises(TypeError):
        vars(base.InterfaceConfig(name="eth0"))


def test_raw_is_never_exposed():
    """`raw` holds the unparsed device output and can carry anything the
    host printed; it has no business in an API response."""
    cfg = base.InterfaceConfig(name="eth0", raw={"secret-ish": "blob"})
    assert "raw" not in _fields(cfg, drop={"raw"})
    assert "raw" not in schemas.InterfaceConfigPublic.model_fields
