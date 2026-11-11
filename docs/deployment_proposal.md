# Deployment proposal — separate frontend hosting

> **Status: proposal for supervisor and team discussion (11 Nov 2026). Not approved and not
> implemented.** This document is a presentation and planning aid. Until a decision is recorded,
> [`architecture.md`](architecture.md) remains the binding system description.

## Purpose

Evaluate hosting the static web frontend separately from the data and application services. The
proposal is based on the team's discussion about Cloudflare Pages and keeping hosting separate
from the server that runs the backend. The phrase “VPS and hosting separate” needs confirmation:
it may mean a rented VPS for the backend, or it may allow the available HP ProDesk to run it.

## Current design

The current architecture describes Caddy on a small external VPS serving the built frontend and
proxying `/api` to FastAPI. PostGIS, Valhalla and the pipeline also run on that server through
Docker Compose. See [`architecture.md`](architecture.md) §§3, 11.

The local `compose.yaml` supports development. Production deployment files and automation are
still planned; see [`implementation_plan.md`](implementation_plan.md) P8. This proposal does not
claim that production deployment is already ready.

## Option for discussion

```text
Visitors
  ├── https://<site-domain> ──> Cloudflare Pages (React/Vite static build)
  └── https://<api-domain> ───> Cloudflare Tunnel ──> server ──> FastAPI
                                                              ├── PostGIS
                                                              └── Valhalla

Scheduled/on-demand refresh ──> pipeline and one-shot tile build on the server
Team administration ──────────> private network access (candidate: Tailscale)
```

Cloudflare Pages would build the `web/` project (`npm run build`, output `dist`). Its
`VITE_API_BASE` build setting would point to a dedicated API hostname. Cloudflare Tunnel is a
candidate for connecting that hostname to the API without accepting direct inbound web traffic on
the server. The public app still needs a publicly reachable API; a tunnel by itself does not
authenticate app visitors. The API's CORS allowlist would need to include the production Pages
origin and any approved preview origins.

All stateful and compute-intensive services would stay together on one backend machine: API,
PostGIS, Valhalla, pipeline, and tile building. PostGIS and Valhalla would remain private. For
team administration, Tailscale is a candidate for private SSH and database access, with separate
accounts and least-privilege database roles. The existing architecture's supervisor access via an
SSH tunnel should be checked against this option before changing it.

### Backend host choices

| Choice | Benefits to evaluate | Constraints to evaluate |
|---|---|---|
| Available HP ProDesk (i5-8500T, 16 GB RAM) | No VPS rental; hardware is available to the team | Home/institutional power and network uptime, remote recovery, storage, backups, and who maintains it |
| Rented VPS | Data-centre power/network and remote management | Monthly cost, provider limits, disk sizing, backups, and measured tile-build capacity |

The ProDesk is an on-premises server, not a VPS. Neither option is selected by this proposal. The
first full tile build and refresh must be measured on the chosen host; disk capacity and speed,
RAM, CPU, and refresh duration should be recorded. The architecture's current resource estimate
is explicitly marked for verification on first deployment (§11).

## Why consider the split

- Keep static frontend hosting separate from the machine doing routing, database and pipeline work.
- Use Pages' Git integration for frontend builds and preview deployments.
- Keep database and routing ports private while exposing only the API endpoint needed by the app.
- Preserve the existing backend service boundaries and data flow; this proposal changes the
  frontend hosting and access/deployment arrangement, not the measurement methodology.

## Decisions needed

1. Does the supervisor approve Cloudflare Pages for the public static frontend?
2. Does “keep VPS and hosting separate” require a rented VPS, or is the ProDesk acceptable as the
   backend host? What uptime is required for the course demonstration?
3. Who owns the domain, Cloudflare account, tunnel credentials, server, backups and incident
   response?
4. Is Tailscale acceptable for private teammate administration, or should the team use an
   alternative such as Cloudflare Access?
5. How should supervisors reach the read-only database account under the selected access model?
6. What are the acceptable backup frequency, recovery time, and measured refresh window?

## If approved: implementation sequence

1. Record the hosting and access decisions with the supervisor and affected folder owners.
2. Update `architecture.md` and its version/change log to describe the approved topology; update
   the implementation plan and README to match.
3. Implement production Compose and server setup, persistent storage, secrets, firewall/tunnel,
   private team access, backups and restore steps.
4. Configure Pages from `web/`, set production build variables, and connect the frontend to the
   API hostname with an explicit CORS allowlist.
5. Deploy to a non-production hostname, verify the app and API, reboot recovery, backup restore,
   and a full refresh on the selected machine before calling the deployment ready.

## Brief for presentation agents

Use this proposal together with [`architecture.md`](architecture.md), not in place of it. Present
the current design first, label the Pages/server split as **proposed**, show both backend-host
choices, and end with the decisions in “Decisions needed”. Do not state that the design is
approved, that production deployment is implemented, or that the ProDesk has passed capacity or
uptime testing.
