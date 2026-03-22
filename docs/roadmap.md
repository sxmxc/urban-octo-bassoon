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
- **Secret boundary first**: runtime credentials must be write-only in the admin experience, never returned after save, and never persisted as plaintext.
- **Credentials separate from connector settings**: per-vendor credential records should hold secret material, while flow nodes keep non-secret operational settings and bind credentials explicitly.
- **API-trigger first**: keep `api_trigger` as the only entry node while the flow UX matures.
- **Self-hosted first**: local Docker and image-only GHCR deployments remain first-class.
- **Typed data ops before raw code**: break the generic `transform` step into explicit data-operation nodes over time, and keep any future script/code node behind a separate sandbox decision.
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
  - credentials (with `/connections` compatibility aliases)
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
- dedicated top-level `Credentials` page for shared HTTP/Postgres credential CRUD with lightweight `project` / `environment` metadata, in-use delete protections, and write-only secret placeholders during edits
- Flow-tab compact connector context (scope/count/refresh + direct link to `Credentials`) while keeping node inspector binding to saved connection ids
- Flow-tab branch-aware logic editing for first-class `If` / `Switch` nodes
- Flow node editing now uses the same input/config/output workbench in standard and full-screen modes, with pinned focus-mode previews, schema/table/json preview modes, embedded payload-tree ref pills for common path-template edits, shared connected-path cards for reconnecting or relabeling outgoing edges, and a focus-toolbar save action that follows the same dirty-state rules as the standard Flow save button
- Flow-canvas rewiring now supports replacement when operators drag from occupied output handles, supports target-side edge retargeting through `edge-update`, and uses distinct node silhouettes by category to improve scanability in larger graphs
- maintained drag-and-drop for the schema editor and Flow palette, replacing bespoke native `dataTransfer` wiring with shared drag-preview/drop-target infrastructure
- shared public-route policy across OpenAPI, `/api/reference.json`, and legacy mock fallback so runtime-managed routes stay public only while they still have an active deployment
- unsupported public `auth_mode` values now fail closed: only `auth_mode = none` routes stay on public contract/runtime surfaces, unsupported auth routes return `501`, and the compiled public deployment registry excludes them until inbound auth lands
- public runtime node failures now omit raw connector/database/runtime detail from public response bodies while still retaining internal `error_message` detail in admin execution traces
- admin login throttling now recovers client IPs from `Forwarded` / `X-Forwarded-For` only when the immediate peer matches configured trusted-proxy CIDRs, and otherwise keeps throttling on the direct socket identity
- viewer roles can no longer read shared credential configs, execution runs, execution details, or execution telemetry; runtime visibility remains editor+
- editor/superuser credential reads now return redacted secret-bearing config fields plus placeholder metadata so stored secrets can survive edit flows without ever being revealed again, including Postgres DSN aliases, case-insensitive HTTP header-name normalization, and explicit clearing when HTTP header payloads are omitted
- runtime traces now apply secret-aware redaction before persistence, and outbound HTTP nodes reject absolute/scheme-relative path overrides plus protected-header collisions
- the old plaintext `Connection.config` blob is gone; non-secret connector settings now persist separately from encrypted secret material, `/api/admin/credentials` is the primary admin API, and `/api/admin/connections` remains as a compatibility alias
- credential encryption now requires `CREDENTIAL_ENCRYPTION_KEY` at API startup and during the storage migration, and both paths resolve it through the same `.env`-aware settings loader; local Compose/test bootstrap stays usable because those flows inject explicit dev/test keys
- explicit disable-live workflow in the admin API and `Deploy` tab, which deactivates the active deployment without deleting route or implementation history
- runtime-aware route deletion for both direct admin deletes and confirmed `replace_all` imports, including explicit cleanup of runtime history before the route row is removed

Still transitional:
- the public runtime still falls back to the legacy schema-driven mock path for routes that have not yet entered the live-runtime lifecycle
- the new Vue Flow editor now supports branching plus pinned node-level sample data/preview inspection, but it still leans on raw JSON entry instead of richer non-JSON data-mapping ergonomics
- the current `transform` node is still a catch-all transitional step; the roadmap is to split it into a typed `Data Ops` family such as `split`, `merge/join`, and related collection/state operators while keeping stored transform definitions backward compatible
- connector scope remains intentionally metadata-first; flow nodes still bind explicit saved connection ids rather than auto-resolving by environment at runtime
- OpenAPI and `/api/reference.json` now follow the shared public-route policy for runtime-managed routes, but legacy-only routes still remain public until the product fully cuts over to deployment-only publishing
- browse telemetry is intentionally derived from recent runtime history in Postgres for now; long-horizon retention, alerting, and time-series offload remain future observability work

## Recommended Implementation Order

### 1. Auth and replay boundary

- keep the temporary unsupported-auth rejection in place until real inbound auth (API keys, bearer policies, scopes) ships
- decide and implement a safe request-body capture/replay policy for execution traces
- keep the credential/key-management boundary explicit as more auth and replay work lands

### 2. Improve operator surfaces

After the above:
- deployment promotion polish
- deeper replay/debug tooling once request-capture retention rules are explicit
- credential/node UX polish plus typed `Data Ops` follow-up work

## Current Runtime Boundaries

These are important and should not be blurred casually:

- `EndpointDefinition` is the route contract and catalog record.
- `RouteImplementation` is the saved live runtime graph.
- `RouteDeployment` is the publish/promotion layer.
- `ExecutionRun` / `ExecutionStep` are runtime traces.
- `response_schema` powers preview/examples generation.
- `flow_definition` powers deployed live execution.
- credentials and other live secrets belong to admin/runtime-only credential stores, not to public contract documents or broad read APIs.

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
