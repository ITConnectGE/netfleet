# ----------------------------------------------------------------
#  NetFleet — Caddy with the Cloudflare DNS module
#
#  The stock `caddy` image only ships the HTTP-01 and TLS-ALPN-01 ACME
#  challenges, and both need the host reachable from the internet on :80/:443.
#  Deployments whose public DNS record points at a private address (no inbound
#  NAT) can only pass DNS-01, which needs a provider module compiled in.
#
#  Enable it with NETFLEET_ACME_DNS=cloudflare in .env — see .env.example.
# ----------------------------------------------------------------

ARG CADDY_VERSION=2.11.4

FROM caddy:${CADDY_VERSION}-builder AS builder
RUN xcaddy build --with github.com/caddy-dns/cloudflare

FROM caddy:${CADDY_VERSION}-alpine
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
