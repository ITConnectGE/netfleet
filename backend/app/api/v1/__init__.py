from fastapi import APIRouter

from app.api.v1 import (
    audit,
    auth,
    backups,
    bulk,
    device_ops,
    devices,
    drivers,
    firewall,
    firmware,
    network,
    oidc,
    queues,
    roles,
    router_system,
    settings as settings_api,
    setup,
    sites,
    system,
    users,
    vpn,
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
router.include_router(vpn.router, prefix="/devices", tags=["vpn"])
router.include_router(firewall.router, prefix="/devices", tags=["firewall"])
router.include_router(router_system.router, prefix="/devices", tags=["router-system"])
router.include_router(network.router, prefix="/devices", tags=["network"])
router.include_router(queues.router, prefix="/devices", tags=["queues"])
router.include_router(backups.router, prefix="/devices", tags=["backups"])
router.include_router(firmware.router, prefix="", tags=["firmware"])
router.include_router(bulk.router, prefix="/bulk", tags=["bulk"])
router.include_router(roles.router, prefix="/roles", tags=["roles"])
router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(audit.router, prefix="/audit", tags=["audit"])
router.include_router(settings_api.router, prefix="/settings", tags=["settings"])

# Health is at the root of /api/v1 for easy probe endpoints
router.add_api_route("/health", system.health, methods=["GET"], tags=["system"])
