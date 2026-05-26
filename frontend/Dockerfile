# syntax=docker/dockerfile:1.7

# ----- Base -----
FROM node:20-alpine AS base
RUN corepack enable && corepack prepare pnpm@9.12.3 --activate
WORKDIR /app

# ----- Deps -----
FROM base AS deps
COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile || pnpm install

# ----- Dev -----
FROM base AS dev
COPY --from=deps /app/node_modules ./node_modules
COPY . .
EXPOSE 3000
CMD ["pnpm", "dev"]

# ----- Build -----
FROM base AS build
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN pnpm build

# ----- Production -----
FROM node:20-alpine AS prod
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1

RUN addgroup -g 1001 -S netfleet && adduser -S netfleet -u 1001 -G netfleet

COPY --from=build --chown=netfleet:netfleet /app/public ./public
COPY --from=build --chown=netfleet:netfleet /app/.next/standalone ./
COPY --from=build --chown=netfleet:netfleet /app/.next/static ./.next/static

USER netfleet
EXPOSE 3000
CMD ["node", "server.js"]
