# Architecture

Artificer is built as a **monorepo** with a public API surface and a private admin studio. The platform is now pivoting from a mock-first product into a route-first API platform, so the architecture is being split more explicitly into a control plane, a production runtime path, and a preview/examples engine.

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
- the route `Test` workspace and dedicated route tester now separate admin contract preview from live/public request execution, with explicit draft/live state summaries
- request/response schema authoring now lives directly in the route `Contract` tab, and legacy schema-editor deep links redirect into that in-workspace journey
- the route `Test` workspace now also supports lazy-loaded execution drill-down plus a replay handoff into the dedicated tester using captured path/query trace data
- the route browse dashboard now also surfaces basic live telemetry from runtime history, including average/p95 latency plus slow-route and slow-flow hotspot summaries
- the deploy surface now supports both publish and disable-live actions against the active deployment
- deployment-backed dispatch exists
- Flow mapping values now support whole-value refs plus inline `{{...}}` interpolation in both live runtime execution and editor sample inspection
- Flow JSON helper pills now support selection-aware drag/drop insertion, so operators can replace the current token or selection instead of resetting the whole editor payload
- the Flow editor now supports first-class `If` / `Switch` logic nodes plus `HTTP Request` and read-only `Postgres Query` nodes backed by shared `Connection` records
- shared connector CRUD now lives on a dedicated top-level `Connectors` page, while the Flow workspace keeps compact route-scoped connection context plus a direct handoff to that page
- the Flow editor now uses the same selected-node input/config/output workbench in both the standard tab layout and the full-screen canvas mode, with pinned previews in focus mode, payload-tree ref pills for common path-template mapping flows, and a focus-toolbar save affordance that shares the standard Flow save state model

## Core components

- **Backend (`apps/api/`)**
  - FastAPI application serving two sets of endpoints:
    - **Admin API / control plane**: bearer-session auth, account-profile endpoints, password rotation, admin roles/permissions, dashboard-user management, CRUD operations for route definitions, plus runtime-backed implementations, deployments, connections, executions, and aggregated execution-telemetry summaries.
    - **Public runtime**: the public catchall now checks a compiled deployment registry first and can execute the first live flow nodes for deployed routes.
    - **Public status/reference**: an API status page at `/status` plus `/api/reference.json`, both driven from the shared public-route selector plus a backend-owned route publication-state model instead of blindly exposing every enabled route. The root `/` now redirects to `/status`, while `/api` intentionally returns no content.
    - **System health**: `/api/health` is now a first-class system endpoint that reports dependency-by-dependency health for the API process, database, deployment registry, public reference generation, and OpenAPI generation.
  - **Postgres** is used as the single source of truth for route definitions, implementations, deployments, connections, admin users, and execution history.
  - Private admin path space such as `/api/admin` is reserved and cannot be claimed by DB-backed public routes.
  - Baseline browser hardening headers now ship from the FastAPI layer, while the admin frontend mirrors them in both Vite dev and the runtime Nginx image.
  - **OpenAPI generation** is performed at runtime from the same shared public-route selector used by the status/reference feed.
  - **Preview/examples generation** still supports fixed, true-random, and mocking-random response values from `response_schema`, explicit semantic value types for context-aware data like IDs, names, emails, prices, and long-form text fields, request-aware string templating through `x-mock.template`, and a deliberately snarkier Artificer voice in `mocking` mode.
  - The live runtime path now includes route implementations, environment deployments, execution traces, a compiled in-memory matcher cache keyed by method/path specificity, first-class `if_condition` / `switch` branch routing, first-class `http_request` / `postgres_query` connector execution, and per-node step timings that can feed the first telemetry summaries without a separate metrics store yet.
  - During the transition, the public catchall still falls back to the legacy mock generator for routes that have not yet entered the live-runtime lifecycle; once a route has a saved implementation/deployment record, it is public only through an active deployment.

- **Frontend (`apps/admin-web/`)**
  - Vue + Vite + Vuetify admin dashboard.
  - Provides route catalog management, browse-mode telemetry summaries, integrated `Contract`-tab schema authoring, preview tools, a personal profile flow, superuser-only user management, auth-protected admin workflows with role-aware UI gating, and route-first tabs for `Overview`, `Contract`, `Flow`, `Test`, and `Deploy`.
  - The schema studio is intentionally pivoting from a bespoke pill-tree drag/drop surface toward a canvas-first architecture, with `Vue Flow` as the leading frontend foundation, while preserving the existing backend JSON Schema contracts.
  - The `Test` surface now lets operators inspect recent `ExecutionRun` traces in-place, expand ordered `ExecutionStep` details on demand, and reopen the dedicated tester with replay context seeded from captured path/query inputs. Request-body replay remains intentionally limited until the runtime trace model grows beyond `body_present`.
  - The `Flow` surface now uses a constrained Vue Flow canvas with an API-first entry node, branch-aware logic/connector palettes, visible branch ports, drag-to-canvas placement, explicit `error_response` routing, selected-node editing that keeps the same input/config/output workbench in both standard and full-screen modes, per-node sample data inspection, inline string/data composition inside mapping JSON, selection-aware helper-pill insertion in JSON editors, and a more canvas-native full-editor mode built around compact floating launchers, a top-center control bar, a MiniMap, node-local toolbars, and pinned input/config/output previews plus path-template-friendly ref pills while preserving the same backend flow-definition model. Route-scoped connector awareness remains in Flow, but full connector credential CRUD is intentionally centralized on the dedicated `Connectors` page.
  - The schema editor and Flow palette now route their bespoke drag interactions through a shared Pragmatic Drag and Drop wrapper, which replaces the older native `dataTransfer` plumbing with maintained drag previews plus richer copy/move drop hooks.
  - Local Docker development uses a Vite-based `dev` image target, while release builds package the compiled SPA behind Nginx in a separate `runtime` target.

- **Orchestration**
  - Uses Docker Compose for local and QA profiles.
  - Services include: Postgres, backend, frontend.
  - GitHub Actions additionally validates runtime images and publishes multi-arch GHCR artifacts for CI/CD.

## Data flow
1. Admin user creates or edits route definitions via the UI.
2. Backend persists route contracts in Postgres and can optionally store a draft `flow_definition` alongside them as a route implementation.
3. Publishing a route implementation creates an active deployment record, while unpublishing deactivates the current deployment without deleting runtime history; both actions invalidate the in-memory runtime registry cache.
4. The public runtime matches incoming requests against compiled active deployments first and executes the branch-aware live flow engine when a deployment exists.
5. Routes with no runtime records still use the existing preview/mock generator during the transition, but routes with saved runtime records are hidden from public fallback unless an active deployment exists.
6. The public status page and `/api/reference.json` read from that same shared public-route policy and route publication-state model, including generated request/response examples.
7. `/api/health` evaluates system dependencies independently instead of relying on a DB-authored mock route.
8. OpenAPI schema is generated from the same shared public-route policy and served on `/openapi.json`.
9. Deleting a route now explicitly clears runtime implementations, deployments, execution runs, and execution steps before removing the route-definition row, and the same cleanup path is used by confirmed `replace_all` imports.

## Immediate next step

The next major implementation task should deepen operator ergonomics without blurring the preview/runtime boundary:
- improve richer non-JSON mapping ergonomics in `Flow`
- keep the preview/runtime split intact while future replay/debug depth is evaluated against request-retention constraints
