# Development Setup

## Prerequisites
- Docker Desktop (or equivalent Docker engine)
- Node.js 24+ for local frontend work
- Python 3.12+ (optional for running backend locally without Docker)

## Quickstart

1. Copy environment defaults:

```sh
cp .env.example .env
```

2. Start all services:

```sh
make up
```

3. Visit the surfaces:
- Public API landing page: http://localhost:8000
- Admin UI: http://localhost:3000
- OpenAPI JSON: http://localhost:8000/openapi.json
- API docs: http://localhost:8000/docs

## Local production-like mode

If you want to run the checked-out repo in a production-like local mode instead of the hot-reload dev stack:

```sh
make up-prod-local
```

That command uses [docker-compose.prod-local.yml](/home/devadmin/projects/urban-octo-bassoon/docker-compose.prod-local.yml), which:

- builds the Dockerfiles' `runtime` targets from your local source tree
- starts the API through `start.prod.sh` without `uvicorn --reload`
- serves the admin app from the built SPA behind Nginx instead of the Vite dev server
- keeps the same service names, default Compose project, and named Postgres volume so Compose recreates the existing stack in place and you can swap between `make up` and `make up-prod-local` without resetting the DB

Stop it with:

```sh
make down-prod-local
```

If you want to remove the production-like local DB volume too:

```sh
make clean-prod-local
```

## Bootstrap notes

- `make up` is safe to run from a bind-mounted checkout even if `start.sh` does not have the executable bit set on the host.
- The repo root includes `.node-version` and `.python-version` files so `nvm`, `mise`, `asdf`, or similar tooling can match the supported local runtimes quickly.
- Local Compose explicitly builds the Dockerfiles' `dev` targets so the API keeps `uvicorn --reload` and the admin app keeps the Vite dev server for fast iteration.
- The local production-like Compose file builds the `runtime` targets instead, so it is useful for smoke-testing the built/Nginx-backed stack before a real deployment.
- API startup now runs `alembic upgrade head` before launching Uvicorn, so schema changes and legacy contract migrations are applied automatically.
- Local Compose now defaults `POSTGRES_VOLUME_NAME` to `urban_octo_bassoon_pgdata` so this checkout does not accidentally keep using the older repo's Postgres volume.
- The frontend keeps `node_modules` in a Docker volume so the bind-mounted source tree does not hide Vite and other installed dependencies.
- The frontend startup script now hashes `package-lock.json` and refreshes the Dockerized dependency volume automatically when the lockfile changes, which helps keep image/runtime dependencies isolated from host `node_modules`.
- For remote or domain-based frontend access, set `FRONTEND_ALLOWED_HOSTS` in `.env` to a comma-separated list such as `localhost,127.0.0.1,docker01.example.internal`.
- The frontend dev proxy target is configurable through `FRONTEND_DEV_PROXY_TARGET`; Docker should point it at `http://api:8000`.
- Postgres health checks now target the configured application database instead of the default user name.
- `make down` removes the named Docker volumes, which is useful if you want a completely fresh database bootstrap and frontend dependency install.
- Alembic config and revisions live under `apps/api/migrations/` inside the API app because that path is available inside the Docker build context.
- Approved public landing artwork can be dropped into `apps/api/static/landing/` as `hero-top.*` and `hero-bottom.*`; a single tall `hero.*` asset remains supported as a fallback.

## Running tests

```sh
make test
```

Frontend checks:

```sh
docker compose run --rm admin-web npm run lint
docker compose run --rm admin-web npm run test
docker compose run --rm admin-web npm run build
```

## Dedicated QA account

For browser-driven verification, first check whether the existing local stack is already serving the app:

```sh
docker compose ps --format json
curl -s http://localhost:8000/api/health
curl -I -s http://localhost:3000
```

If those checks fail or a required service is missing, start only what is needed. For agent/browser work, prefer detached startup over a foreground `make up` session:

```sh
docker compose up --build -d
```

Then create or reset a dedicated admin account instead of reusing the shared bootstrap login:

```sh
make ui-test-user UI_TEST_ADMIN_USERNAME=ui-agent
```

Notes:
- Reuse an already-running stack when possible instead of bouncing containers or trying to reclaim the same ports for a "fresh" session.
- Test usernames must start with `ui-`, `qa-`, or `test-`; the helper refuses to manage the shared bootstrap admin account.
- The helper is idempotent. Re-running it resets the named account's password, reactivates the account, and updates its profile fields.
- Leaving `UI_TEST_ADMIN_*` unset preserves the helper defaults (`ui-agent`, `UI Test Agent`, `editor`) instead of forwarding blank overrides into Docker.
- If no password file is provided, the helper generates a one-time password and prints it to stdout.
- To set a known password without putting it in shell history, write it to a local file and pass `UI_TEST_ADMIN_PASSWORD_FILE=/absolute/path/to/password.txt`.
- The default role is `editor`. Set `UI_TEST_ADMIN_ROLE=superuser` if the account needs access to `/users` or other superuser-only flows.
- For repeated browser or AI-driven sessions, prefer stable dedicated usernames such as `ui-feature-agent` or `ui-tester-agent` plus a password file so the session can be recreated predictably.
- The helper runs through the API container, applies migrations first, and keeps the normal auth model intact; it does not add a special unauthenticated API shortcut.

## Runtime images

- The production-ready image targets are `runtime`, not the `dev` targets used by local Compose.
- The API runtime image reads `APP_VERSION` so published OpenAPI metadata can match the release tag.
- The admin runtime image serves the built SPA through Nginx and proxies `/api` to `API_UPSTREAM` (default `http://api:8000`).
- The GitHub image workflow validates `runtime` builds on pull requests and publishes multi-arch images on `main` and `v*` tags.

## Local development (backend only)

You can run the backend directly:

```sh
cd apps/api
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Local development (frontend only)

```sh
cd apps/admin-web
npm install
npm run dev
```

If you prefer staying Docker-first, `make lint` now runs the frontend linter inside the `admin-web` container instead of requiring host-installed dependencies.

## Vuetify MCP

- The repo root includes a `.mcp.json` entry for the hosted Vuetify MCP server at `https://mcp.vuetifyjs.com/mcp`.
- The frontend package also includes local scripts:

```sh
cd apps/admin-web
npm run mcp:vuetify
npm run mcp:vuetify:http
```

- If your IDE prefers user-level MCP configuration, the official `@vuetify/mcp` docs support `npx -y @vuetify/mcp config --remote` for the hosted server or `npx -y @vuetify/mcp config` for a local stdio setup.
