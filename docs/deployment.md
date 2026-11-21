# Deployment — reach

> **Status:** v1.0 draft (21 Nov 2026). How code reaches users: environments, workflows, secrets,
> required checks and the server runbook. Architecture: [`architecture.md`](architecture.md) §11.
> Parts that depend on open decisions (Cloudflare product in S0.5, D1–D4 in S1.2) are marked.

## Principles

- Nobody deploys by hand. Work happens on topic branches → draft PR into `dev`; a release PR
  `dev` → `main` (2 approvals) is the only way to production.
- The push to `main` runs `deploy.yml`, which deploys everything, checks that it works and rolls
  back if not.
- Secrets are created by a team member (Rico), never by an agent, and never printed in logs.
- Data never passes through GitHub or Cloudflare; the data refresh runs on the server.
- PostGIS, Valhalla and the transit engine are never reachable from the internet.

## Environments

| Environment | Frontend | Backend | Data |
|---|---|---|---|
| Local | `npm run dev` (*planned, S0.5*) | `make up` (*planned, S0.4*) | test clip or Tübingen |
| CI | build + Playwright with API fixtures | disposable PostGIS for contract tests; Docker builds without push | fixtures in the repo |
| Preview | Cloudflare preview per same-repository PR and for `dev` | none or production API read-only (D4) | fixtures or production (D4) |
| Production | Cloudflare production | server (D1) via tunnel or Caddy (D2) | weekly refresh on the server |

## Workflows (*planned, S0.5*)

### `ci.yml`

Triggers: pull requests, push to `dev`. Jobs (names become the required checks):

| Job | Does |
|---|---|
| `python` | `uv sync --frozen`, `ruff check`, `ruff format --check`, `pytest` |
| `db-contract` | `pytest -m db` against a disposable PostGIS service container |
| `web` | `npm ci`, `npm run lint`, `npm run build`, Playwright with API fixtures |
| `docker-build` | builds `api` and `pipeline` images (and the transit engine image if separate), no push |
| `preview` | deploys the web build to a Cloudflare preview; URL in the run summary; skipped for fork PRs (no secrets) |

### `deploy.yml`

Triggers: push to `main`; `workflow_dispatch` with inputs `sha` and `target` (redeploy, rollback
or a preview test). `workflow_dispatch` works only once the workflow exists on the default branch
`dev` (GitHub docs, checked 21 Nov 2026). Environment `production` (deployment branch rule:
`main` only); `concurrency: deploy` without cancelling a running deploy.

1. `ci` — the CI jobs on the merge commit (reusable workflow).
2. `images` — build and push `api`, `pipeline` (and transit engine if separate) to GHCR, tagged
   with the commit SHA (`permissions: packages: write` only here).
3. `frontend` — deploy the web build to Cloudflare production with the official Wrangler action,
   pinned to a commit SHA.
4. `backend` — on the server: pull images by SHA, run migrations, `docker compose -f
   compose.prod.yaml up -d`, keep data volumes. **Skipped with a warning while the server secrets
   are missing** (until S1.5).
5. `smoke` — on the public URLs: frontend loads; API health; one fit request with a persona; one
   cell request (fit and cell from S1.10).
6. `rollback` — if `smoke` fails: redeploy the previous successful SHA (backend and frontend),
   fail the run, post to the team webhook.
7. `summary` — SHA, image tags, URLs, smoke-test results in the run summary.

## Secrets and variables

Created by Rico. Names are fixed here; values never appear in the repository or in logs.

### GitHub (Settings → Environments → `production`, unless noted)

| Name | Kind | Purpose | Minimal scope | Needed from |
|---|---|---|---|---|
| `CLOUDFLARE_API_TOKEN` | secret | Wrangler deploys of the frontend | Custom token, one account, only the deploy permission of the chosen product (Pages: *Cloudflare Pages — Edit*; Workers static assets: *Workers Scripts — Edit*); exact set confirmed in S0.5 | S0.5 |
| `CLOUDFLARE_ACCOUNT_ID` | variable | Target account for Wrangler | not secret | S0.5 |
| `TEAM_WEBHOOK_URL` | secret | Failure message of deploy and rollback | incoming webhook of the team chat, posting only | S0.5 |
| backend access (`DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS` for SSH, or tunnel credentials) | secrets | Backend job reaches the server | deploy-only user, key without passphrase used only for this; exact list after D2 | S1.5 |

Where the preview job gets its Cloudflare token (the `production` environment only admits `main`)
is decided in the S0.5 step plan. `GITHUB_TOKEN` is used for GHCR pushes; no extra token.

**Creating the Cloudflare token** (S0.5, after the product choice): Cloudflare dashboard → My
Profile → API Tokens → Create Token → Custom token → Permissions: *Account* → the product's
deploy permission → *Edit*; Account Resources: *Include* → the team account; no zone permissions;
TTL until 28 Feb 2027 → Continue → Create → copy once into GitHub: repository → Settings →
Environments → `production` → Add environment secret `CLOUDFLARE_API_TOKEN`.

### Server `.env` (never in GitHub)

| Name | Purpose |
|---|---|
| `POSTGRES_PASSWORD` | PostGIS superuser (migrations only) |
| `APP_READ_PASSWORD`, `PIPELINE_WRITE_PASSWORD`, `SUPERVISOR_READ_PASSWORD` | DB roles (`supervisor_read` [VERIFY], A5) |
| `FAILURE_WEBHOOK_URL` | Failure message of the scheduled refresh |
| `GHCR_READ_TOKEN` | Only if the images are private: pull from GHCR (classic token, `read:packages`) |
| tunnel token | Only if D2 = tunnel |

All variables with comments: [`.env.example`](../.env.example).

## Required status checks on `dev`

Set by Rico after S0.5 (Settings → Branches → `dev` → Require status checks): `python`,
`db-contract`, `web`, `docker-build`. `preview` stays optional (fork PRs skip it).

## Release procedure

1. Release PR `dev` → `main`, title `chore(release): vX.Y.Z`: moves `Unreleased` in
   `CHANGELOG.md` to a version section, bumps the versions; body lists what changes for users.
2. Socke and Juju approve; a human merges.
3. `deploy.yml` deploys; the run summary is linked in the release notes. Tags and GitHub Releases
   only on explicit instruction.

## Server runbook (*outline; full version after D1–D2, S1.2/S1.5*)

1. Book the server (D1) — Rico, never an agent.
2. Base setup: updates, non-root admin user, SSH keys of the team, no password login, firewall
   (D2: tunnel = no inbound ports except SSH; Caddy = 22 and 443), swap.
3. Docker Engine + Compose plugin; deploy user (if SSH deploy).
4. Checkout of `compose.prod.yaml` and `config/`; `.env` from `.env.example` with real values.
5. `make migrate`; first `make refresh`; check the validation report.
6. Enable the scheduled refresh (S3.1) and backups (S3.2).
7. Add the backend secrets to GitHub; run `deploy.yml` via `workflow_dispatch` on `dev` against
   the server; then the rollback test with a deliberately broken SHA.
