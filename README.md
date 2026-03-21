# Artificer

[![CI](https://github.com/sxmxc/artificer/actions/workflows/ci.yml/badge.svg)](https://github.com/sxmxc/artificer/actions/workflows/ci.yml)
[![Container Images](https://github.com/sxmxc/artificer/actions/workflows/images.yml/badge.svg)](https://github.com/sxmxc/artificer/actions/workflows/images.yml)
[![Version](https://img.shields.io/badge/version-2.0.0--alpha.3-22d3ee?style=flat-square&logo=github&logoColor=white)](VERSION)
[![Docs](https://img.shields.io/badge/docs-roadmap%20%2B%20architecture-8b95a7?style=flat-square&logo=gitbook&logoColor=white)](docs/roadmap.md)
[![Vue](https://img.shields.io/badge/Vue-3-4FC08D?style=flat-square&logo=vuedotjs&logoColor=white)](https://vuejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0F766E?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Vuetify](https://img.shields.io/badge/Vuetify-4-1867C0?style=flat-square&logo=vuetify&logoColor=white)](https://vuetifyjs.com/)

Artificer is a Docker-first, route-first API platform for designing, testing, publishing, and operating configurable API routes through a dedicated control plane. The platform is split into Artificer API for the public/runtime surface and Artificer Studio for the private admin experience.

The current system already includes a live public API status page, dynamic OpenAPI, a private admin dashboard, and the first deployment-backed runtime scaffolding for published route implementations. The older schema-driven mock generator still powers previews, examples, and fallback behavior while the live runtime grows into the primary execution path.

## At A Glance

| Surface | Purpose | Local URL |
| --- | --- | --- |
| `Status` | Public API status page and route reference | `http://localhost:8000/status` |
| `Studio` | Private admin workspace | `http://localhost:3000` |
| `OpenAPI` | Published machine contract | `http://localhost:8000/openapi.json` |
| `Docs` | Developer references and architecture notes | `README.md`, `docs/` |

Current direction:

- route-first API platform instead of a mock-only editor
- explicit `Overview`, `Contract`, `Flow`, `Test`, and `Deploy` workflows
- deployment-backed runtime execution with publish/unpublish semantics
- stronger operator tooling around connections, execution traces, and runtime debugging
- richer flow-authoring ergonomics, especially around mapping, data-shape visibility, and modern drag-and-drop interactions

## 🚀 Quickstart (Local)

1. Copy `.env.example` to `.env` and adjust as desired.
2. Start services:

```sh
make up
```

3. Open the product surfaces:

- Public API status page: http://localhost:8000/status
- Artificer Studio: http://localhost:3000
- OpenAPI JSON: http://localhost:8000/openapi.json
- FastAPI docs: http://localhost:8000/docs and http://localhost:8000/redoc

If `ADMIN_BOOTSTRAP_PASSWORD` is left blank, the API prints a one-time bootstrap password in its startup logs the first time it creates the initial admin account. That account must rotate its password before the rest of the admin API unlocks.

If you access the frontend through a remote host or internal DNS name, add it to `FRONTEND_ALLOWED_HOSTS` in `.env`. When the frontend runs in Docker, keep `FRONTEND_DEV_PROXY_TARGET=http://api:8000`.

## 🧪 Production-Like Local Mode

If you want to run your checked-out repo with the runtime targets instead of the hot-reload dev stack:

```sh
make up-prod-local
```

That local production-like mode:

- builds the API `runtime` target, which starts with `start.prod.sh` and runs without `uvicorn --reload`
- builds the admin `runtime` target, which serves the built SPA through Nginx instead of the Vite dev server
- keeps the same service names, default Compose project, and Postgres volume so Compose recreates the existing stack in place and you can swap back to `make up` without losing your local catalog data

Stop it with:

```sh
make down-prod-local
```

If you want to wipe the local production-like database volume too:

```sh
make clean-prod-local
```

## 🧠 What You Get Today

- **Route catalog and contracts**: routes stored in Postgres remain the source of truth for route metadata, request/response schemas, and OpenAPI publishing.
- **Deployment-backed runtime foundation**: draft route implementations, deployments, execution traces, shared connections, and the first compiled in-memory route registry are now part of the backend foundation.
- **Flow editor foundation**: the admin UI includes a Vue Flow-based authoring surface for live route implementations, with starter runtime nodes, branching, connector nodes, and a focused full-editor mode.
- **Preview/examples engine**: schema-driven sample generation still powers route previews, examples, and legacy mock behavior during the transition to fully live implementations.
- **Public API status page**: `/status` renders a Bulma-based API status surface with dependency-by-dependency health checks, backend-owned route publication-state badges, quick-reference table filtering, pagination, request/response example modals for body-based routes, and a light/dark theme toggle, while `/` redirects there and `/api` returns no content.
- **System health endpoint**: `/api/health` is now a system-owned health check that reports overall status plus dependency-by-dependency checks for the API process, database, deployment registry, public reference generation, and OpenAPI generation.
- **Live OpenAPI**: `/openapi.json` reflects the active route catalog.
- **Admin API**: bearer-session admin routes manage endpoint definitions, route implementations, deployments, connections, execution history, and dashboard accounts in Postgres.
- **Seed catalog**: `make seed` loads 14 sample endpoints for local exploration, including device examples that now use UUID-style `deviceId` values and a curated default model enum.
- **Admin UI**: Vue + Vuetify route management now includes dedicated sign-in, protected route-first Overview/Contract/Flow/Test/Deploy surfaces, integrated Contract-tab schema authoring, and live previews of generated/public examples.
- **Admin UI**: Vue + Vuetify route management now includes dedicated sign-in, protected route-first Overview/Contract/Flow/Test/Deploy surfaces, integrated Contract-tab schema authoring, a collapsible route catalog rail for wider editing space, and live previews of generated/public examples.
- **Schema-driven generation**: response schemas can mix static values, true random generation, and mocking-style random generation per field via internal `x-mock` extensions, with semantic value types like `id`, `name`, `email`, `price`, and `long_text`.
- **Vuetify AI support**: the frontend uses `@vuetify/v0` for theme/storage helpers and ships with a repo-level Vuetify MCP config.
- **Docker-first**: one command to bring up the full stack without depending on host `node_modules` for the frontend container.

## 📦 Architecture

- **Backend**: FastAPI + SQLModel + Postgres
- **Frontend**: Vue + Vite + TypeScript + Vuetify
- **DB migrations**: Alembic
- **Orchestration**: Docker Compose

## 🛣️ Direction

The near-term ambition is to make the published runtime the product center of gravity:

- contracts stay distinct from live implementations
- `Deploy` becomes the real publish boundary for public/runtime surfaces
- `Flow` becomes the place where operators define behavior, not just mock output
- `Test` becomes explicit about preview vs live execution
- connections, execution traces, and runtime debugging become first-class

This fork is not trying to become a generic workflow builder. The core model remains API-triggered routes with contract-aware live behavior.

## 🚢 CI/CD

- GitHub Actions CI now runs backend tests, frontend lint/test/build, and a Docker Compose smoke test on `main` pushes and pull requests.
- GitHub Actions CI also checks that every version consumer stays in sync with the repo-root `VERSION` file.
- Runtime container images are built from dedicated `runtime` Docker targets rather than the local hot-reload targets used by `make up`.
- The image workflow validates runtime images on pull requests and publishes multi-arch `linux/amd64` + `linux/arm64` images to GHCR on `main` and `v*` tags.
- Release tags follow `ghcr.io/<owner>/artificer-api` and `ghcr.io/<owner>/artificer-studio` with:
  - `vX.Y.Z`, `X.Y`, `X`, and `latest` for semver tags
  - branch, `edge`, and `sha-<commit>` tags for default-branch builds
- Each image build also uploads metadata artifacts and provenance so digests/tags are easy to inspect in Actions.

Local release/version helpers:

- `make version`
- `make version-check`
- `make set-version VERSION=2.0.0-alpha.2`
- `make bump-version PART=prerelease PRE_LABEL=alpha`

## 📁 Repo layout

- `apps/api/` - Backend implementation
- `apps/admin-web/` - Admin UI
- `apps/api/migrations/` - Alembic migrations
- `apps/api/scripts/` - DB init and seed scripts
- `docs/` - Architecture, strategy, and how-tos
- `deploy/` - Standalone deployment examples that reference published GHCR images
- Root tracking docs - `TASKS.md`, `MEMORY.md`, `DECISIONS.md`

See `docs/ci-cd.md` for the release workflow, image tag rules, and runtime environment notes.

## 📚 Documentation

- Canonical docs live in this repo: [`README.md`](README.md) and [`docs/`](docs/)
- The practical user/developer handbook lives in the [GitHub Wiki](https://github.com/sxmxc/artificer/wiki)
- The implementation handoff / platform direction doc lives in [`docs/roadmap.md`](docs/roadmap.md)
- The admin UI guide lives in [`docs/admin-ui.md`](docs/admin-ui.md)

## 🐳 Image-only Compose Example

If you want to run Artificer without cloning the full repo, start from:

- `deploy/docker-compose.ghcr.yml`
- `deploy/.env.ghcr.example`

Those files default to:

- `${IMAGE_REPOSITORY}-api`
- `${IMAGE_REPOSITORY}-studio`

The current fork ships with:

- `IMAGE_REPOSITORY=ghcr.io/sxmxc/artificer`

The default `IMAGE_TAG=edge` tracks the latest default-branch publish. For release deployments, prefer an explicit tag such as `IMAGE_TAG=1.2.3`.

If you already have the repo checked out and just want a local runtime smoke test, use:

- `docker-compose.prod-local.yml`
- `make up-prod-local`

## 🧩 Next steps

Check `TASKS.md` for what to work on next.
If you are picking up implementation work, read `docs/roadmap.md` and `docs/architecture.md` first.
