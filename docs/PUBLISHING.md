# Publishing NetFleet — first push to GitHub + first release

This walks you through getting the repo on `github.com/ITConnectGE/netfleet`,
building the first set of Docker images, and confirming the in-app updater works.

> Until you complete step 5 (tag + release), the production `docker compose up`
> will fail because the `ghcr.io/itconnectge/netfleet-*` images don't exist yet.
> Use the **dev compose** (step 6) until then.

---

## 1. Pre-flight checklist

Before pushing **anywhere**, confirm there are no secrets in the working tree:

```bash
# From D:\Mikrotik-Central
git init
git add .
git status

# A real .env file MUST NOT appear in the output.
# Only .env.example should show up. .gitignore already excludes .env.

# Look for accidental private keys / credentials:
grep -RIn "BEGIN.*PRIVATE KEY" . 2>/dev/null || echo "✅ no private keys"
grep -RIn "password = \"" . 2>/dev/null | grep -v "node_modules\|.git\|example" || echo "✅ no inline passwords"
```

## 2. Create the GitHub repo

On GitHub:

1. Go to `github.com/organizations/ITConnectGE`
2. **New repository**:
   - Name: `netfleet`
   - Description: `Open-source multi-vendor network fleet management for MSPs`
   - Visibility: **Public**
   - **Do NOT** initialize with README / .gitignore / license (we have ours)
3. Click *Create repository*. Copy the URL.

## 3. First commit

```bash
git config user.name "Your Name"
git config user.email "you@itconnectge.ge"

git remote add origin git@github.com:ITConnectGE/netfleet.git
# or HTTPS: git remote add origin https://github.com/ITConnectGE/netfleet.git

git add .
git commit -m "feat: initial release — Phases 1-6a (skeleton, auth, RBAC, fleet, secret audit)

NetFleet is a multi-vendor network fleet management platform for MSPs.

Shipped:
- Docker Compose stack (Caddy + Postgres + Redis + API + Web + Worker + Updater)
- Auth: local + TOTP + Entra ID OIDC, JWT with rotated refresh tokens
- Granular RBAC: per-section, per-action, scoped to org/site/device
- Sites + Devices CRUD with encrypted credentials, vendor driver abstraction
- MikroTik driver: system info, DHCP leases, firewall/NAT, IP services,
  device users (with bulk password reset), PPP secrets, WireGuard, backup
- Audit log with payload redaction + UI
- Secret reveal audit + departing-user risk report

See docs/ROADMAP.md for what's coming next."
git branch -M main
git push -u origin main
```

## 4. Configure repo settings

In the GitHub UI:

- **Settings → Actions → General → Workflow permissions**: Read and write permissions ✅
- **Settings → Packages → Manage Actions access**: ensure the repo can push to ghcr.io (default OK on new repos)
- **Settings → General**: add topics `mikrotik`, `mikrotik-api`, `network-management`, `msp`, `network-monitoring`, `routeros`, `fastapi`, `nextjs`, `self-hosted`

## 5. Tag v0.1.0 to trigger the first release

```bash
git tag v0.1.0
git push origin v0.1.0
```

This fires `.github/workflows/release.yml`. Watch it under the **Actions** tab.

If green, three images are now on `ghcr.io`:
- `ghcr.io/itconnectge/netfleet-api:0.1.0` (and `:latest`, `:stable`, `:0.1`)
- `ghcr.io/itconnectge/netfleet-web:0.1.0`
- `ghcr.io/itconnectge/netfleet-updater:0.1.0`

**Make the packages public** (they default to private on first push):

1. `github.com/orgs/ITConnectGE/packages` → click each `netfleet-*` package
2. Package settings → **Change visibility** → Public

Without this, `docker pull ghcr.io/itconnectge/netfleet-api:latest` returns 401.

## 6. Boot the stack — two paths

### Path A — dev mode (always works, builds locally)

```bash
cd D:\Mikrotik-Central
cp .env.example .env
# Open .env and set:
#   NETFLEET_DOMAIN=localhost
#   NETFLEET_JWT_SECRET=$(openssl rand -hex 32)
#   NETFLEET_FERNET_KEY=$(python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())")
#   NETFLEET_UPDATER_TOKEN=$(openssl rand -hex 32)
#   NETFLEET_DB_PASSWORD=$(openssl rand -hex 24)
#   NETFLEET_DATABASE_URL=postgresql+asyncpg://netfleet:<that password>@postgres:5432/netfleet

docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Open <http://localhost:3000>.

### Path B — production-style (requires step 5 done)

```bash
sudo bash install.sh   # prompts for domain, generates .env, pulls images
```

Or manual:

```bash
cd /opt/netfleet
cp .env.example .env   # edit, set domain + secrets
docker compose up -d   # pulls from ghcr.io
```

## 7. End-to-end smoke test

1. Browser → `https://your-domain` (or `http://localhost:3000` in dev)
2. Middleware redirects to `/setup` (because the DB is empty)
3. Create org + admin user (password ≥ 12 chars)
4. `/login` → enter email + password → land on `/dashboard`
5. Create a site (`Client A`)
6. Add a MikroTik device with its host/user/password
7. Open device → **Test connection** — should flip to **online**
8. Try **IP services** tab — RouterOS service list appears
9. Try **Device users** tab — list of router-local users

If any step fails, see [PROGRESS.md § Things NOT yet exercised](PROGRESS.md#things-not-yet-exercised) — the stack has not been booted end-to-end yet; the first time you run it you'll likely hit one or two small migration / config bugs that need cleaning up.

## 8. Subsequent updates via the UI (the dream)

Once v0.1.0 is live:

1. Develop Phase 6b locally
2. Commit, push to `main`
3. Bump version in `backend/app/__init__.py` and `frontend/package.json` to `0.2.0`
4. `git tag v0.2.0 && git push origin v0.2.0`
5. Wait for the release workflow to publish images
6. Open NetFleet in your browser — **a banner appears**: "v0.2.0 available"
7. Click **Update Now**, optionally confirm pre-update backup
8. Updater pulls images → recreates `api`/`web`/`worker` → Alembic migrates
9. Page refreshes on the new version

> Phase 1 ships the updater as a **stub** — it polls GitHub Releases and returns
> status correctly, but the actual `docker compose pull && up -d` flow is **wired
> in Phase 7**. Until then, manual updates: `docker compose pull && docker compose up -d`.

## 9. README badge update (after first release)

Once images are public on ghcr.io, update the README badges:

```markdown
[![Docker pulls](https://img.shields.io/badge/ghcr.io-itconnectge%2Fnetfleet-blue)](https://github.com/orgs/ITConnectGE/packages?repo_name=netfleet)
[![Latest release](https://img.shields.io/github/v/release/ITConnectGE/netfleet)](https://github.com/ITConnectGE/netfleet/releases/latest)
```

---

## TL;DR commands

```bash
# 1. push to GitHub (run from D:\Mikrotik-Central)
git init
git add .
git commit -m "feat: initial release"
git branch -M main
git remote add origin https://github.com/ITConnectGE/netfleet.git
git push -u origin main

# 2. trigger first release build
git tag v0.1.0
git push origin v0.1.0

# 3. make packages public in the GitHub UI (one-time)

# 4. boot locally (dev mode — always works)
cp .env.example .env  # then edit secrets
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```
