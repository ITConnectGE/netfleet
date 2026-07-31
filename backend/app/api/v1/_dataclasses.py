"""Dataclass -> response-model plumbing.

Shared so every endpoint module converts the same way. `dataclasses.fields`
rather than `vars()`: every driver dataclass is declared `slots=True`, so
instances have no `__dict__` and `vars()` raises TypeError — which is how
three endpoints returned a 500 apiece in 0.47.0.
"""

from __future__ import annotations

from dataclasses import fields as dataclass_fields
from typing import Any


def fields(obj: Any, *, drop: frozenset[str] | set[str] = frozenset()) -> dict[str, Any]:
    """Every field of a dataclass instance, minus the ones the public shape
    omits. Listing them by hand instead would drift the moment a dataclass
    gains one."""
    return {
        f.name: getattr(obj, f.name)
        for f in dataclass_fields(obj)
        if f.name not in drop
    }
