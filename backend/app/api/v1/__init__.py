from fastapi import APIRouter

from app.api.v1 import (
    audit,
    auth,
    bulk,
    device_ops,
    devices,
    drivers,
    oidc,
    roles,
    setup,
    sites,
    system,
    users,
)

router = APIRouter()

router.include_router(system.router, prefix="/system", tags=["system"])
router.include_router(setup.router, prefix="/setup", tags=["setup"])
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(oidc.router, prefix="/auth/oidc", tags=["auth"])
router.include_router(drivers.router, prefix="/drivers", tags=["drivers"])
router.include_router(sites.router, prefix="/sites", tags=["sites"])
router.include_router(devices.router, prefix="/devices", tags=["devices"])
router.include_router(device_ops.router, prefix="/devices", tags=["device-ops"])
router.include_router(bulk.router, prefix="/bulk", tags=["bulk"])
router.include_router(roles.router, prefix="/roles", tags=["roles"])
router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(audit.router, prefix="/audit", tags=["audit"])

# Health is at the root of /api/v1 for easy probe endpoints
router.add_api_route("/health", system.health, methods=["GET"], tags=["system"])
