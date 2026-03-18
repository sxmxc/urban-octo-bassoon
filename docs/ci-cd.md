# CI/CD

## Overview

- `CI` runs on `main` pushes and pull requests.
- `Container Images` runs on pull requests, `main` pushes, `v*` tags, and manual dispatches.
- Local Docker Compose keeps using `dev` image targets; published images use the Dockerfiles' `runtime` targets.

## CI workflow

- The workflows opt into `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true` so JavaScript actions are exercised on the Node 24 runtime before GitHub makes that the default runner behavior.
- Backend job: Python 3.12 via `actions/setup-python@v6`, installs `requirements.txt` and `requirements-dev.txt`, then runs `pytest`.
- Frontend job: Node 24 via `actions/setup-node@v6`, runs `npm ci`, `npm run lint`, `npm run test`, and `npm run build`.
- Docker smoke job: copies `.env.example` to `.env`, runs `docker compose up -d --build`, waits for the API and admin UI to answer, then tears the stack down.

## Image workflow

- Pull requests: build-only validation of the `runtime` targets on `linux/amd64`.
- `main` pushes and `workflow_dispatch`: publish `linux/amd64,linux/arm64` images to GHCR.
- `vX.Y.Z` tags: publish official multi-arch release images to GHCR.

Published image names:

- `ghcr.io/<owner>/<repo>-api`
- `ghcr.io/<owner>/<repo>-admin-web`

For this repo, that resolves to:

- `ghcr.io/sxmxc/urban-octo-bassoon-api`
- `ghcr.io/sxmxc/urban-octo-bassoon-admin-web`

## Tagging and versioning

- `vX.Y.Z` tags publish:
  - `X.Y.Z`
  - `X.Y`
  - `X`
  - `latest`
- Default-branch builds publish:
  - the branch tag (for example `main`)
  - `edge`
  - `sha-<short-sha>`
- Pull request builds generate PR/SHA metadata tags for validation but do not push images.
- The API image passes `APP_VERSION` into the container so FastAPI/OpenAPI version metadata can match the published build.

## Build artifacts

Each image run uploads a metadata artifact containing:

- image name
- resolved version
- digest
- tags
- Docker build metadata JSON
- published manifest JSON when the image was pushed

Pushed images also emit provenance/SBOM data through the image workflow.

## Dependency posture

- Backend audits are expected to stay clean under `pip-audit -r requirements.txt -r requirements-dev.txt`.
- Frontend audits are expected to stay clean under `npm audit`.
- The admin frontend now uses ESLint flat config, so `npm ci` should no longer emit the old deprecated-package warnings from the ESLint 8 toolchain.
- `npm outdated` still reports a newer `vue-router` major; that remains a conscious follow-up rather than part of the dependency/security refresh.

## Runtime environment notes

- API runtime:
  - command: `sh ./start.prod.sh`
  - still runs migration/bootstrap on startup
  - honors `API_HOST`, `API_PORT`, and `APP_VERSION`
- Admin runtime:
  - serves static assets with Nginx
  - proxies `/api` to `API_UPSTREAM`
  - defaults `API_UPSTREAM` to `http://api:8000`

## Standalone Compose

- `deploy/docker-compose.ghcr.yml` is the example Compose file for environments that do not have the repo checked out.
- `deploy/.env.ghcr.example` is the companion env template.
- The example now uses `IMAGE_REPOSITORY` so the fork can be retargeted without editing the Compose file itself.
- The example defaults to `IMAGE_TAG=edge` so it can track the latest default-branch image, but production deployments should pin an explicit release tag such as `1.2.3`.
