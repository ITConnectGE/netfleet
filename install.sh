#!/usr/bin/env bash
# ------------------------------------------------------------------
#  NetFleet — one-command installer for Ubuntu 22.04 / 24.04
#  Usage:   curl -fsSL https://raw.githubusercontent.com/ITConnectGE/netfleet/main/install.sh | sudo bash
#  Or:      sudo ./install.sh
# ------------------------------------------------------------------
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/netfleet}"
REPO="${REPO:-ITConnectGE/netfleet}"
BRANCH="${BRANCH:-main}"
COLOR_GREEN="\033[0;32m"
COLOR_YELLOW="\033[1;33m"
COLOR_RED="\033[0;31m"
COLOR_RESET="\033[0m"

log()  { echo -e "${COLOR_GREEN}[netfleet]${COLOR_RESET} $*"; }
warn() { echo -e "${COLOR_YELLOW}[netfleet] warning:${COLOR_RESET} $*"; }
die()  { echo -e "${COLOR_RED}[netfleet] error:${COLOR_RESET} $*" >&2; exit 1; }

# --- preflight ---
[[ $EUID -eq 0 ]] || die "must run as root (use sudo)"

if ! grep -qi "ubuntu\|debian" /etc/os-release; then
  warn "tested only on Ubuntu 22.04/24.04 — proceeding anyway"
fi

ARCH="$(uname -m)"
log "host: $(uname -srm)"
log "install dir: $INSTALL_DIR"

# --- Docker ---
if ! command -v docker >/dev/null 2>&1; then
  log "installing Docker Engine..."
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
else
  log "Docker present: $(docker --version)"
fi

if ! docker compose version >/dev/null 2>&1; then
  die "Docker Compose plugin missing. Install docker-compose-plugin and re-run."
fi

# --- directories ---
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/data/"{postgres,redis,backups,caddy,caddy-config}
mkdir -p "$INSTALL_DIR/data/backups/devices"
chmod 700 "$INSTALL_DIR/data/postgres"
# postgres:16-alpine runs as UID 70 — the data dir must be writable by it.
chown -R 70:70 "$INSTALL_DIR/data/postgres"

# --- secrets ---
gen_hex() { openssl rand -hex 32; }
# Fernet keys are 32 random bytes in url-safe base64, padding included
# (44 characters ending in "="). No Python needed: a fresh Ubuntu often
# has no `cryptography` module, and the old openssl fallback produced a
# 43-character standard-base64 string that Fernet rejects, so the API
# crashed on its first start.
gen_fernet() { openssl rand 32 | base64 | tr '+/' '-_' | tr -d '\n'; }
valid_fernet() { [[ "$1" =~ ^[A-Za-z0-9_-]{43}=$ ]]; }
valid_domain() { [[ "$1" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ ]]; }
env_get() { grep -m1 "^$1=" "$INSTALL_DIR/.env" | cut -d= -f2- | tr -d "\"'\r" || true; }

# The domain comes from $NETFLEET_DOMAIN, else from the terminal. Under
# `curl ... | sudo bash` stdin is the script itself, so a plain `read`
# would swallow the next line of this file as the "domain".
ask_domain() {
  local d="${NETFLEET_DOMAIN:-}"
  if [[ -z "$d" ]] && { exec 3</dev/tty; } 2>/dev/null; then
    read -rp "Enter the domain that will serve NetFleet (e.g. netfleet.example.com): " d <&3 || true
    exec 3<&-
  fi
  if [[ -z "$d" ]]; then
    d="localhost"
    warn "no domain given (set NETFLEET_DOMAIN=... to choose one); using localhost"
  fi
  valid_domain "$d" || die "'$d' is not a valid domain name or IP address"
  DOMAIN="$d"
}

set_domain() {
  sed -i \
    -e "s|^NETFLEET_DOMAIN=.*|NETFLEET_DOMAIN=$DOMAIN|" \
    -e "s|^NETFLEET_PUBLIC_URL=.*|NETFLEET_PUBLIC_URL=https://$DOMAIN|" \
    -e "s|^NETFLEET_OIDC_REDIRECT_URI=.*|NETFLEET_OIDC_REDIRECT_URI=https://$DOMAIN/api/v1/auth/oidc/callback|" \
    -e "s|^NETFLEET_CORS_ORIGINS=.*|NETFLEET_CORS_ORIGINS=https://$DOMAIN|" \
    -e "s|^NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=https://$DOMAIN/api/v1|" \
    "$INSTALL_DIR/.env"
}

if [[ ! -f "$INSTALL_DIR/.env" ]]; then
  log "fetching .env.example..."
  curl -fsSL "https://raw.githubusercontent.com/$REPO/$BRANCH/.env.example" \
    -o "$INSTALL_DIR/.env"

  JWT=$(gen_hex)
  FERNET=$(gen_fernet)
  UPDATER_TOKEN=$(gen_hex)
  DB_PASS=$(gen_hex | head -c 24)
  # First-run takeover defence — the very first POST /api/v1/setup must
  # carry this token in `X-Bootstrap-Token`. The token is consumed by the
  # `is_setup_complete=True` DB transition, so it is single-use even though
  # we don't delete the .env line. See backend/app/api/v1/setup.py.
  BOOTSTRAP_TOKEN=$(gen_hex)

  ask_domain

  sed -i \
    -e "s|^NETFLEET_JWT_SECRET=.*|NETFLEET_JWT_SECRET=$JWT|" \
    -e "s|^NETFLEET_FERNET_KEY=.*|NETFLEET_FERNET_KEY=$FERNET|" \
    -e "s|^NETFLEET_UPDATER_TOKEN=.*|NETFLEET_UPDATER_TOKEN=$UPDATER_TOKEN|" \
    -e "s|^NETFLEET_BOOTSTRAP_TOKEN=.*|NETFLEET_BOOTSTRAP_TOKEN=$BOOTSTRAP_TOKEN|" \
    -e "s|^NETFLEET_DB_PASSWORD=.*|NETFLEET_DB_PASSWORD=$DB_PASS|" \
    -e "s|^NETFLEET_DATABASE_URL=.*|NETFLEET_DATABASE_URL=postgresql+asyncpg://netfleet:$DB_PASS@postgres:5432/netfleet|" \
    "$INSTALL_DIR/.env"
  set_domain

  chmod 600 "$INSTALL_DIR/.env"
  log "generated $INSTALL_DIR/.env with fresh secrets"
else
  log ".env already exists — keeping current values"
  # Repair what earlier versions of this script got wrong. Both made the
  # API fail on its first start, so nothing was ever encrypted with the
  # bad key and nothing was served on the bad domain: replacing them is safe.
  if ! valid_fernet "$(env_get NETFLEET_FERNET_KEY)"; then
    warn "NETFLEET_FERNET_KEY in .env is not a valid Fernet key — generating a new one"
    sed -i "s|^NETFLEET_FERNET_KEY=.*|NETFLEET_FERNET_KEY=$(gen_fernet)|" "$INSTALL_DIR/.env"
  fi
  if ! valid_domain "$(env_get NETFLEET_DOMAIN)"; then
    warn "NETFLEET_DOMAIN in .env is not a valid domain — asking again"
    ask_domain
    set_domain
  fi
fi

# --- compose & Caddyfile ---
for f in docker-compose.yml Caddyfile; do
  if [[ ! -f "$INSTALL_DIR/$f" ]]; then
    log "fetching $f..."
    curl -fsSL "https://raw.githubusercontent.com/$REPO/$BRANCH/$f" -o "$INSTALL_DIR/$f"
  fi
done

# --- pull & start ---
cd "$INSTALL_DIR"
log "pulling images..."
docker compose pull
log "starting stack..."
if ! docker compose up -d; then
  echo
  warn "the stack did not start. Last API log lines:"
  docker compose logs --tail 40 api || true
  die "start failed — see the log above, or run: docker compose -f $INSTALL_DIR/docker-compose.yml logs api"
fi

log "waiting for healthchecks..."
for _ in {1..30}; do
  if docker compose ps --format json 2>/dev/null | grep -q '"Health":"healthy"'; then
    break
  fi
  sleep 2
done

log "done."
DOMAIN_USED=$(grep '^NETFLEET_DOMAIN=' "$INSTALL_DIR/.env" | cut -d= -f2)
TOKEN_USED=$(grep '^NETFLEET_BOOTSTRAP_TOKEN=' "$INSTALL_DIR/.env" | cut -d= -f2)
echo
echo -e "${COLOR_GREEN}=========================================================${COLOR_RESET}"
echo -e "  ${COLOR_GREEN}NetFleet is up.${COLOR_RESET}"
echo
if [[ -n "$TOKEN_USED" ]]; then
  # Token after the `#` is a URL fragment — fragments are not sent to the
  # server in the request line, never land in access logs, the Referer
  # header, or upstream proxy caches. The web setup page picks it up from
  # window.location.hash and forwards it as the X-Bootstrap-Token header.
  echo -e "  ${COLOR_GREEN}First-run setup URL${COLOR_RESET} (single use, share with care):"
  echo
  echo -e "    https://$DOMAIN_USED/setup#token=$TOKEN_USED"
  echo
  echo -e "  Token also stored in $INSTALL_DIR/.env (mode 600)"
  echo -e "  as NETFLEET_BOOTSTRAP_TOKEN. Once the first admin is created,"
  echo -e "  the endpoint refuses further setup attempts and the token is"
  echo -e "  effectively dead."
else
  echo -e "  Open: https://$DOMAIN_USED"
fi
echo -e "${COLOR_GREEN}=========================================================${COLOR_RESET}"
echo
echo "Logs:    docker compose -f $INSTALL_DIR/docker-compose.yml logs -f"
echo "Stop:    docker compose -f $INSTALL_DIR/docker-compose.yml down"
echo "Update:  via the in-app UI  (Settings → Updates)"
echo
