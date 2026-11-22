# Deployment — reach

> **Status:** v1.0 draft (21 Nov 2026). How code reaches users: environments, workflows, secrets,
> required checks and the server runbook. Architecture: [`architecture.md`](architecture.md) §11.
> Cloudflare product checked in S0.5 (Workers static assets); parts that depend on D1–D4 (S1.2)
> are marked.

## Principles

- Nobody deploys by hand. Work happens on topic branches → draft PR into `dev`; a release PR
  `dev` → `main` (2 approvals) is the only way to production.
- The push to `main` runs `deploy.yml`, which deploys everything, checks that it works and rolls
  back if not.
- Secrets are created by a team member, never by an agent, and never printed in logs.
- Data never passes through GitHub or Cloudflare; the data refresh runs on the server.
- PostGIS, Valhalla and the transit engine are never reachable from the internet.

## Environments

| Environment | Frontend | Backend | Data |
|---|---|---|---|
| Local | `cd web && npm run dev` (proxies `/api` to the local API) | `make up` | test clip or Tübingen |
| CI | build + Playwright with API fixtures | disposable PostGIS for contract tests; Docker builds without push | fixtures in the repo |
| Preview | Cloudflare Workers Preview `pr-<number>` per same-repository PR, `dev` for the dev branch, `deploy-test` for a dispatch test | none or production API read-only (D4) | fixtures or production (D4) |
| Production | Cloudflare Worker `reach` (static assets) | server (D1) via tunnel or Caddy (D2) | weekly refresh on the server |

## Cloudflare product and billing (checked 22 Nov 2026)

The frontend is a **Worker with static assets** (`web/wrangler.jsonc`: `assets.directory = ./dist`,
`not_found_handling = single-page-application`, empty `previews` block), not Cloudflare Pages.
Workers static assets is the settled choice for this static Vite SPA. Cloudflare's current billing
docs say static asset requests are free and unlimited, with no asset storage charge. A request
that invokes Worker code is billed under Workers pricing; we do not currently need request-time
Worker code. Pages static requests are also free, so billing alone does not distinguish the two.
See [Workers static asset billing](https://developers.cloudflare.com/workers/static-assets/billing-and-limitations/),
[Workers pricing](https://developers.cloudflare.com/workers/platform/pricing/), and
[Pages Functions pricing](https://developers.cloudflare.com/pages/functions/pricing/). Recheck
pricing if request-time Worker logic or another paid Cloudflare product is added.

Previews: `wrangler preview --name <name>` creates or
updates a Preview of the same Worker at `<name>-reach.<subdomain>.workers.dev` with its own
settings; Preview URLs are public ([Previews](https://developers.cloudflare.com/workers/previews/)).
Production URL: `reach.<subdomain>.workers.dev` until D3. Deploys use the official
[`cloudflare/wrangler-action`](https://github.com/cloudflare/wrangler-action) pinned to a commit
SHA, with Wrangler pinned in the workflows (`WRANGLER_VERSION`). The API and pipelines remain on
the project server; Cloudflare hosts the frontend assets only.

## Workflows

### `ci.yml`

Triggers: pull requests, push to `dev`, and `workflow_call` from `deploy.yml` (input `ref` = the
SHA being deployed). Jobs (names become the required checks):

| Job | Does |
|---|---|
| `python` | installs `osmium-tool`, `uv sync --frozen`, `ruff check`, `ruff format --check`, `pytest` |
| `db-contract` | `pytest -m db` against a disposable `imresamu/postgis:18-3.6` service container |
| `web` | `npm ci`, `npm run lint`, `npm run build`, Playwright (Chromium desktop + mobile) with API fixtures; report uploaded on failure |
| `docker-build (api)`, `docker-build (pipeline)` | build the images without push (GitHub Actions cache) |
| `preview` | builds the web app and runs `wrangler preview --name pr-<number>` (PR) or `--name dev` (push to `dev`); checks that the URL serves this SHA; URL in the run summary and as deployment URL. Skipped for fork PRs and inside `deploy.yml`; **passes with a warning while `CLOUDFLARE_API_TOKEN` is missing** in the environment `preview` |

### `deploy.yml`

Triggers: push to `main`; `workflow_dispatch` with inputs `sha` (empty = head of the selected
branch) and `target` (`preview` default, or `production`). `workflow_dispatch` works only once the
workflow exists on the default branch `dev` (GitHub docs, checked 21 Nov 2026). `target:
production` is refused unless the run starts from `main` and the SHA is on `main`; a preview
dispatch from any branch tests the whole flow without touching production.
`concurrency: deploy` without cancelling a running deploy; top-level `permissions: {}`, each job
declares its own.

1. `resolve` — resolves the SHA and the target; picks the environment (`production` or `preview`).
2. `ci` — `ci.yml` on that SHA (reusable workflow).
3. `images` — build and push `ghcr.io/<owner>/reach-api` and `reach-pipeline`, tagged with the
   full SHA (`packages: write` only here, `GITHUB_TOKEN`).
4. `frontend` — build with `VITE_BUILD_SHA` and `VITE_API_BASE`, then `wrangler deploy`
   (production) or `wrangler preview --name deploy-test` (preview). No npm cache in jobs that
   publish.
5. `backend` — **skipped with a warning while `DEPLOY_HOST` is missing** (until S1.5); fails if
   the server secrets exist before the deploy steps are written (S1.5).
6. `smoke` — Playwright smoke tests against the deployed URL: page loads, shows the deployed SHA
   (also in `<meta name="build-sha">`), deep links fall back to the app. API health, fit and cell
   requests are added with the backend (S1.5/S1.10).
7. `rollback` — production only, if `smoke` or `backend` failed: rebuilds and redeploys the last
   SHA a push to `main` deployed successfully (`wrangler deploy`); backend rollback follows in
   S1.5. Not `wrangler rollback`: without a version id it returns to the version *uploaded*
   before the latest, which may never have been live.
8. `report` — SHA, target, URL, image tags and job results in the run summary; on any failure a
   message to `TEAM_WEBHOOK_URL` (`{"text": …}`) and a failed run.

## Secrets, variables and settings

Created by a team member, never by an agent. Names are fixed here; values never appear in the
repository or in logs.

### Cloudflare (once)

1. Account: Workers & Pages → set the `workers.dev` subdomain (shown on first visit).
2. API token: My Profile or Manage Account → **Account API Tokens** → Create Token → template
   **Edit Cloudflare Workers** (as recommended in Cloudflare's
   [GitHub Actions guide](https://developers.cloudflare.com/workers/ci-cd/external-cicd/github-actions/))
   → Account Resources: only the team account; Zone Resources: none needed while we use
   `workers.dev` (if the form insists, a single zone) → TTL until 28 Feb 2027 → Create → copy once
   into the GitHub secrets below. The same token may serve both environments; two tokens can be
   revoked separately.
3. Account ID: Workers & Pages overview, right column.

### GitHub (Settings → Environments)

**`production`** — Deployment branches: *Selected branches* → `main` only.

| Name | Kind | Purpose | Needed from |
|---|---|---|---|
| `CLOUDFLARE_API_TOKEN` | secret | `wrangler deploy` of the frontend and rollback | S0.6 |
| `CLOUDFLARE_ACCOUNT_ID` | variable | target account for Wrangler | S0.6 |
| `TEAM_WEBHOOK_URL` | secret | failure message of deploy and rollback (incoming webhook, posting only); optional, a warning if missing | S0.6 |
| `WEB_URL` | variable | production URL, fallback if Wrangler prints none (`https://reach.<subdomain>.workers.dev`) | S0.6 |
| `API_BASE` | variable | public API URL for the web build; leave unset until the backend runs | S1.5 |
| backend access (`DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS` for SSH, or tunnel credentials) | secrets | backend job reaches the server; exact list after D2 | S1.5 |

**`preview`** — Deployment branches: *No restriction* (PR branches and `dev` deploy previews).

| Name | Kind | Purpose | Needed from |
|---|---|---|---|
| `CLOUDFLARE_API_TOKEN` | secret | `wrangler preview` in `ci.yml` and preview dispatches | S0.5 |
| `CLOUDFLARE_ACCOUNT_ID` | variable | target account | S0.5 |
| `PREVIEW_API_BASE` | variable | API URL for previews; unset = previews show "API not deployed yet" (D4) | optional |
| `TEAM_WEBHOOK_URL` | secret | failure message of preview dispatches | optional |

Risk: a secret in `preview` is usable by workflows on any branch of this repository, and the
Cloudflare token can also deploy production. Anyone with write access could misuse it; fork PRs
cannot. Accepted for a three-person team (notes N12); required reviewers on `preview` would stop
every PR preview.

**Repository settings:** Actions → General → Workflow permissions: *Read repository contents*
(jobs ask for more themselves). GHCR: the first `images` run creates the packages `reach-api` and
`reach-pipeline` in the organisation; the organisation must allow members/Actions to create
packages, and package visibility decides whether the server needs `GHCR_READ_TOKEN`.

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

Set after the S0.5 PR has run once (Settings → Branches → `dev` → Require status checks): `python`,
`db-contract`, `web`, `docker-build (api)`, `docker-build (pipeline)`. `preview` stays optional
(fork PRs skip it).

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
