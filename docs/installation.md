# Installation

## One-command install (Ubuntu 22.04 / 24.04)

```bash
curl -fsSL https://raw.githubusercontent.com/ITConnectGE/netfleet/main/install.sh | sudo bash
```

The installer prompts for your domain, generates secrets, and starts the stack.

## Manual install

```bash
git clone https://github.com/ITConnectGE/netfleet.git /opt/netfleet
cd /opt/netfleet
cp .env.example .env
$EDITOR .env
docker compose up -d
```

## DNS

Point an A record at the host's public IP **before** starting NetFleet — Caddy
needs DNS to issue the Let's Encrypt certificate automatically.

```
netfleet.example.com.   A   203.0.113.10
```

## Firewall

Open inbound:
- `80/tcp` — Let's Encrypt HTTP-01 challenge + auto-redirect to HTTPS
- `443/tcp` — HTTPS
- `443/udp` — HTTP/3 (QUIC), optional

The MikroTik/FortiGate/etc. devices that NetFleet manages must be reachable
*outbound* from the host on the device's API port (e.g. 8728/8729 for RouterOS).

## First-time setup

After install:
1. Open `https://your-domain`
2. Create the initial admin account (the local user; this becomes the org owner)
3. (Optional) Settings → Authentication → enable Microsoft Entra ID
4. Settings → Sites → add a Site (e.g. "Client A")
5. Devices → Add device → choose MikroTik, enter host + credentials
6. Test connection — you should see system info populated
7. Settings → Roles → create granular roles for your IT support staff
8. Users → invite team members and assign roles

## Updating

NetFleet updates itself from within the UI: **Settings → Updates → Update Now**.

The updater container:
1. Polls GitHub Releases (`ITConnectGE/netfleet`) every hour
2. Shows a banner when a newer version is available
3. On click, takes a pre-update `pg_dump` to `/opt/netfleet/data/backups/`
4. Pulls the new images and recreates `api`, `web`, `worker`
5. Runs Alembic migrations on the new `api` startup
6. Health-checks; rolls back on failure

For air-gapped or pinned-version installs, set `NETFLEET_UPDATE_CHANNEL=manual`.

## Backups

`/opt/netfleet/data/postgres` and `/opt/netfleet/data/backups` are the only
directories you need to back up. The rest is stateless.

Recommended:
```bash
0 2 * * * docker compose -f /opt/netfleet/docker-compose.yml exec -T postgres \
    pg_dump -U netfleet netfleet | gzip > /opt/netfleet/data/backups/nightly-$(date +\%F).sql.gz
```

## Uninstall

```bash
cd /opt/netfleet
docker compose down              # keeps volumes (data preserved)
# or, to wipe everything:
docker compose down -v
rm -rf /opt/netfleet
```
