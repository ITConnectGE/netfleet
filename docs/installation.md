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

### Internal-only deployments

If the A record points at a private address (RFC1918) because the host has no
inbound NAT, Let's Encrypt cannot reach it and the default HTTP-01 challenge
can never succeed. Caddy will still serve the certificate it already holds, so
the deployment looks healthy right up to the day that certificate expires.

Use the DNS-01 challenge instead — it proves ownership by writing a TXT record,
and needs no inbound connectivity at all. For a zone hosted on Cloudflare:

1. Create an API token at https://dash.cloudflare.com/profile/api-tokens with
   the single permission **Zone → DNS → Edit**, scoped to that zone.
2. Set both values in `/opt/netfleet/.env`:

   ```
   NETFLEET_ACME_DNS=cloudflare
   NETFLEET_CLOUDFLARE_API_TOKEN=<token>
   ```

3. `docker compose up -d caddy` — Caddy re-issues within a minute or so.
   Watch it with `docker compose logs -f caddy`.

Caddy waits 60 seconds after writing the TXT record and then asks Let's
Encrypt to validate. It skips its usual propagation check, which queries the
zone's nameservers directly on port 53 and times out on hosts with outbound
DNS blocked. If the host can reach them, set
`NETFLEET_ACME_PROPAGATION_TIMEOUT=2m` to turn the check back on; if
validation fails on a slow zone, raise `NETFLEET_ACME_PROPAGATION_DELAY`.

Only the Cloudflare provider is compiled into `netfleet-caddy` (see
`caddy/Dockerfile`); another provider means adding its module there and
rebuilding.

## Firewall

Open inbound:
- `80/tcp` — Let's Encrypt HTTP-01 challenge + auto-redirect to HTTPS
- `443/tcp` — HTTPS
- `443/udp` — HTTP/3 (QUIC), optional

Internal-only deployments on DNS-01 need neither `80/tcp` inbound from the
internet nor any port-forward — only outbound HTTPS to Let's Encrypt and the
Cloudflare API. The host clock must also be accurate (NTP, `123/udp` outbound):
ACME rejects requests signed with a badly skewed clock.

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
