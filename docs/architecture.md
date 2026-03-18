# Architecture

Mockingbird is built as a **monorepo** with a public API surface and a private admin studio. The platform is now pivoting from a mock-first product into a route-first API platform, so the architecture is being split more explicitly into a control plane, a production runtime path, and a preview/examples engine.

## Design goals

- Keep the public API contract route-first and backend-owned.
- Keep live implementations separate from public request/response schemas.
- Keep preview/examples generation available without requiring production connections.
- Keep the first live runtime synchronous, typed, and operationally boring.
- Keep Docker-first local development and self-hosted deployment straightforward.

## Current milestone

The current milestone is the **first branch-aware live-flow slice**:
- backend runtime scaffolding is in place
- admin workflow tabs are in place
- deployment-backed dispatch exists
- the Flow editor now supports first-class `If` / `Switch` logic nodes plus `HTTP Request` and read-only `Postgres Query` nodes backed by shared `Connection` records

## Core components

- **Backend (`apps/api/`)**
  - FastAPI application serving two sets of endpoints:
    - **Admin API / control plane**: bearer-session auth, account-profile endpoints, password rotation, admin roles/permissions, dashboard-user management, CRUD operations for route definitions, plus new scaffolding for route implementations, deployments, connections, and executions.
    - **Public runtime**: the public catchall now checks a compiled deployment registry first and can execute the first live flow nodes for deployed routes.
    - **Public landing/reference**: a branded homepage at `/` and `/api` plus `/api/reference.json`, both driven from the route catalog. The landing hero can read approved frame artwork from `apps/api/static/landing/`.
  - **Postgres** is used as the single source of truth for route definitions, implementations, deployments, connections, admin users, and execution history.
  - Private admin path space such as `/api/admin` is reserved and cannot be claimed by DB-backed public routes.
  - Baseline browser hardening headers now ship from the FastAPI layer, while the admin frontend mirrors them in both Vite dev and the runtime Nginx image.
  - **OpenAPI generation** is performed at runtime from the active route catalog.
  - **Preview/examples generation** still supports fixed, true-random, and mocking-random response values from `response_schema`, explicit semantic value types for context-aware data like IDs, names, emails, prices, and long-form text fields, request-aware string templating through `x-mock.template`, and a deliberately snarkier Mockingbird voice in `mocking` mode.
  - The live runtime path now includes route implementations, environment deployments, execution traces, a compiled in-memory matcher cache keyed by method/path specificity, first-class `if_condition` / `switch` branch routing, and first-class `http_request` / `postgres_query` connector execution.
  - During the transition, the public catchall still falls back to the legacy mock generator for routes that have not been published through the new deployment path yet.

- **Frontend (`apps/admin-web/`)**
  - Vue + Vite + Vuetify admin dashboard.
  - Provides route catalog management, a dedicated schema studio, preview tools, a personal profile flow, superuser-only user management, auth-protected admin workflows with role-aware UI gating, and new route-first tabs for `Overview`, `Contract`, `Flow`, `Test`, and `Deploy`.
  - The schema studio is intentionally pivoting from a bespoke pill-tree drag/drop surface toward a canvas-first architecture, with `Vue Flow` as the leading frontend foundation, while preserving the existing backend JSON Schema contracts.
  - The `Flow` surface now uses a constrained Vue Flow canvas with an API-first entry node, branch-aware logic/connector palettes, visible branch ports, drag-to-canvas placement, explicit `error_response` routing, inspector editing, and a more canvas-native full-editor mode built around compact floating launchers, a top-center control bar, a MiniMap, and node-local toolbars while preserving the same backend flow-definition model.
  - Local Docker development uses a Vite-based `dev` image target, while release builds package the compiled SPA behind Nginx in a separate `runtime` target.

- **Orchestration**
  - Uses Docker Compose for local and QA profiles.
  - Services include: Postgres, backend, frontend.
  - GitHub Actions additionally validates runtime images and publishes multi-arch GHCR artifacts for CI/CD.

## Data flow
1. Admin user creates or edits route definitions via the UI.
2. Backend persists route contracts in Postgres and can optionally store a draft `flow_definition` alongside them as a route implementation.
3. Publishing a route implementation creates a deployment record and invalidates the in-memory runtime registry cache.
4. The public runtime matches incoming requests against compiled active deployments first and executes the branch-aware live flow engine when a deployment exists.
5. Routes without a live deployment still use the existing preview/mock generator during the transition.
6. The public landing page and `/api/reference.json` continue to read the route catalog for a live quick reference, including generated request/response examples.
7. OpenAPI schema is generated from the same route catalog and served on `/openapi.json`.

## Immediate next step

The next major implementation task should be to tighten the published-runtime boundary so public docs and live dispatch converge more cleanly:
- keep `request_schema` / `response_schema` as the published contract source of truth
- keep `flow_definition` as the live implementation format
- move OpenAPI and `/api/reference.json` closer to published deployment truth
- preserve the current preview/runtime split so connector secrets stay out of public contract surfaces
- after that, deepen Flow UX around data mapping, input/output previews, and pinned sample data rather than adding non-API trigger families
