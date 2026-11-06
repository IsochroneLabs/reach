# Web image (arch. §10, P6): the static Vite build of web/ served by Caddy, which also proxies
# /api to the API. Build from the repository root: docker build -f infra/web.Dockerfile .
# Node 24 LTS (web/.nvmrc) for the build only; both images are amd64 + arm64.
FROM node:24.22.2-alpine3.24 AS build
WORKDIR /web
# Dependencies first, so source changes do not reinstall them.
COPY web/package.json web/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM caddy:2.11.7-alpine
COPY infra/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /web/dist /srv
