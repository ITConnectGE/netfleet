"""
NetFleet vendor drivers.

Each driver implements the `VendorDriver` Protocol from `app.drivers.base`
and is registered in `app.drivers.registry`. The API layer is vendor-agnostic
— it looks up the driver by `device.vendor` and dispatches calls to it.

Adding a new vendor:
1. Create `app/drivers/<vendor>.py` implementing `VendorDriver`
2. Add it to `_REGISTRY` in `app/drivers/registry.py`
3. Declare its `capabilities: set[Capability]`
4. Add integration tests in `tests/drivers/test_<vendor>.py`

See `app/drivers/mikrotik.py` as the reference implementation.
"""

from app.drivers.base import (
    Capability,
    DhcpLease,
    NatRule,
    SystemInfo,
    VendorDriver,
)
from app.drivers.registry import get_driver, list_vendors

__all__ = [
    "Capability",
    "DhcpLease",
    "NatRule",
    "SystemInfo",
    "VendorDriver",
    "get_driver",
    "list_vendors",
]
