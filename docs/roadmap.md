# Roadmap

This document is the quickest way for the next agent to understand where the platform is headed, what has already landed, and what should happen next.

## Product Direction

The product is being repositioned from a mock-first API tool into a **route-first API platform**.

The core experience should be:
- define a route contract first
- attach a live implementation behind that contract
- preview and test safely
- publish a deployment into a runtime registry
- inspect executions after live traffic hits the route

The product is intentionally **not** becoming a generic automation builder. It should feel closer to:
- API-triggered workflow orchestration
- contract-first API design
- production-safe integration flows

## Design Goals

- **Route-first**: every workflow begins with an HTTP route contract.
- **Backend-owned contracts**: `request_schema` and `response_schema` remain the public contract source of truth.
- **Separate live runtime**: `flow_definition` must stay distinct from the public contract.
- **Preview/runtime boundary**: preview/examples generation stays separate from deployed runtime execution.
- **Sync first**: the first live runtime slice stays synchronous and bounded.
- **Connector-first expansion**: start with `HTTP` and read-only `Postgres`.
- **API-trigger first**: keep `api_trigger` as the only entry node while the flow UX matures.
- **Self-hosted first**: local Docker and image-only GHCR deployments remain first-class.
- **No arbitrary code execution yet**: safe, typed nodes come before script/code nodes.

## Current Milestone

The repo has completed the **pivot foundation milestone**.

Already shipped:
- route-first product framing in repo/docs
- `RouteImplementation`, `RouteDeployment`, `Connection`, `ExecutionRun`, and `ExecutionStep` models
- Alembic migration for the new runtime tables
- deployment-backed runtime registry in `apps/api/app/services/route_runtime.py`
- live executor with these node types:
  - `api_trigger`
  - `validate_request`
  - `transform`
  - `if_condition`
  - `switch`
  - `http_request`
  - `postgres_query`
  - `set_response`
  - `error_response`
- admin API endpoints for:
  - current route implementation
  - deployments, publish, and unpublish
  - connections
  - executions
  - execution telemetry overview
- admin route workspace tabs:
  - `Overview`
  - `Contract`
  - `Flow`
  - `Test`
  - `Deploy`
- schema authoring now lives directly under the route `Contract` journey, and legacy `/endpoints/:id/schema` links redirect into that tab
- a clearer `Test` journey and dedicated route tester that now separate admin contract previews from live/public requests and label live versus draft runtime state explicitly
- execution drill-down in the `Test` workspace, including lazy-loaded run details, ordered step traces, and a replay handoff into the dedicated tester with captured path/query inputs prefilled when available
- browse-dashboard telemetry cards for recent live runs, average/p95 response time, slow routes, and slow flow hotspots derived from runtime history
- shared Flow value rendering for runtime and editor inspection, so transform/response mappings can combine whole-value refs with inline `{{...}}` string interpolation
- selection-aware quick-ref drag/drop in Flow JSON editors, so helper pills replace the current token/selection instead of clobbering the whole draft payload
- Flow-tab inspector support for binding HTTP and Postgres nodes to saved shared connections
- dedicated top-level `Connectors` page for shared connection CRUD (create/edit/retire/reactivate/delete) with lightweight `project` / `environment` metadata and in-use delete protections
- Flow-tab compact connector context (scope/count/refresh + direct link to `Connectors`) while keeping node inspector binding to saved connection ids
- Flow-tab branch-aware logic editing for first-class `If` / `Switch` nodes
- Flow node editing now uses the same input/config/output workbench in standard and full-screen modes, with pinned focus-mode previews, schema/table/json preview modes, embedded payload-tree ref pills for common path-template edits, and a focus-toolbar save action that follows the same dirty-state rules as the standard Flow save button
- maintained drag-and-drop for the schema editor and Flow palette, replacing bespoke native `dataTransfer` wiring with shared drag-preview/drop-target infrastructure
- shared public-route policy across OpenAPI, `/api/reference.json`, and legacy mock fallback so runtime-managed routes stay public only while they still have an active deployment
- explicit disable-live workflow in the admin API and `Deploy` tab, which deactivates the active deployment without deleting route or implementation history
- runtime-aware route deletion for both direct admin deletes and confirmed `replace_all` imports, including explicit cleanup of runtime history before the route row is removed

Still transitional:
- the public runtime still falls back to the legacy schema-driven mock path for routes that have not yet entered the live-runtime lifecycle
- the new Vue Flow editor now supports branching plus pinned node-level sample data/preview inspection, but it still leans on raw JSON entry instead of richer non-JSON data-mapping ergonomics
- connector scope remains intentionally metadata-first; flow nodes still bind explicit saved connection ids rather than auto-resolving by environment at runtime
- OpenAPI and `/api/reference.json` now follow the shared public-route policy for runtime-managed routes, but legacy-only routes still remain public until the product fully cuts over to deployment-only publishing
- browse telemetry is intentionally derived from recent runtime history in Postgres for now; long-horizon retention, alerting, and time-series offload remain future observability work

## Recommended Implementation Order

### 1. Improve operator surfaces

After the above:
- deployment promotion polish
- deeper replay/debug tooling once request-capture retention rules are explicit
- deployment promotion polish

## Current Runtime Boundaries

These are important and should not be blurred casually:

- `EndpointDefinition` is the route contract and catalog record.
- `RouteImplementation` is the saved live runtime graph.
- `RouteDeployment` is the publish/promotion layer.
- `ExecutionRun` / `ExecutionStep` are runtime traces.
- `response_schema` powers preview/examples generation.
- `flow_definition` powers deployed live execution.

Do not:
- generate OpenAPI from flow internals
- shove connector behavior into `x-mock`
- make the preview engine depend on production-only secrets/connections

## Current Hotspots

If the next task is connector/operator follow-up, start here:
- `apps/api/app/services/route_runtime.py`
- `apps/admin-web/src/components/RouteFlowEditor.vue`
- `apps/admin-web/src/views/EndpointsView.vue`
- `apps/admin-web/src/types/endpoints.ts`

## Verification Expectations

Before closing the next major task, verify at least:
- `python3 -m compileall apps/api/app`
- `cd apps/admin-web && npm run typecheck`
- targeted frontend tests for touched views
- `docker compose run --rm api pytest tests/test_api.py -q`
- `docker compose up -d --build` smoke if the change affects startup/runtime behavior
