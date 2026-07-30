"""Driver registry — single source of truth for vendor → driver mapping."""

from __future__ import annotations

from app.drivers.base import VendorDriver
from app.drivers.linux import LinuxDriver
from app.drivers.mikrotik import MikrotikDriver

_REGISTRY: dict[str, VendorDriver] = {
    MikrotikDriver.vendor: MikrotikDriver(),
    LinuxDriver.vendor: LinuxDriver(),
}


def get_driver(vendor: str) -> VendorDriver:
    try:
        return _REGISTRY[vendor]
    except KeyError as e:
        available = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise ValueError(
            f"No driver registered for vendor '{vendor}'. Available: {available}"
        ) from e


def list_vendors() -> list[dict[str, object]]:
    """Used by the UI to render the 'add device' vendor dropdown."""
    return [
        {
            "vendor": d.vendor,
            "display_name": d.display_name,
            "capabilities": sorted(c.value for c in d.capabilities),
        }
        for d in _REGISTRY.values()
    ]
