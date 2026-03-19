# Domain Model

## EndpointDefinition
Represents the route-definition layer for a managed API endpoint. This is still the public contract source of truth during the transition.

Fields:
- `id`: UUID
- `name`: human-friendly label
- `slug`: machine-friendly internal identifier used for seed/import/admin bookkeeping, auto-generated from the route name for admin-created routes
- `method`: HTTP method (GET, POST, etc.)
- `path`: URI path (e.g., `/api/quotes`)
- `category`: grouping (e.g., `quotes`, `users`)
- `tags`: list of tags
- `summary` / `description`: OpenAPI description fields
- `enabled`: boolean
- `auth_mode`: none/basic/api_key/bearer
- `request_schema`: JSON Schema request contract; the body schema lives at the root, while optional path/query parameter metadata lives under `x-request`
- `response_schema`: JSON Schema for response body plus internal builder/generator extensions
- `success_status_code`: default successful response status
- `error_rate`: ratio of requests that return an error in the legacy preview/mock path
- `latency_min_ms`, `latency_max_ms`: simulated delay controls for the legacy preview/mock path
- `seed_key`: deterministic seed for repeatable generated examples
- `created_at`, `updated_at`: audit timestamps

## RouteImplementation
Represents a saved live implementation for a route definition.

Fields:
- `id`: integer primary key
- `route_id`: owning `EndpointDefinition`
- `version`: monotonically increasing implementation version
- `is_draft`: whether this implementation is still editable
- `flow_definition`: graph metadata for the live runtime
- `created_at`, `updated_at`: audit timestamps

Current flow contract:
- Exactly one `api_trigger` node
- Exactly one `set_response` node
- Optional `error_response` node
- Current supported node types: `api_trigger`, `validate_request`, `transform`, `if_condition`, `switch`, `http_request`, `postgres_query`, `set_response`, `error_response`
- The live runtime is now branch-aware rather than strictly linear: `if_condition` routes to one `true` and one `false` edge, `switch` routes to one or more `case` edges plus one required `default` edge, and every reachable main-path branch must still eventually lead into `set_response` or a connected `error_response` terminal
- Mapping-oriented node config values can either resolve a whole value via `{"$ref":"..."}` or interpolate refs inline inside strings with `{{request.path.id}}`, `{{request.body.foo}}`, or `{{state.transform.bar}}`
- Nodes may also carry editor-only layout metadata such as canvas `position`; the backend runtime ignores that UI metadata and continues to execute from node `type`, `name`, `config`, and `edges`

## RouteDeployment
Represents a published implementation bound to an environment.

Fields:
- `id`: integer primary key
- `route_id`: owning route definition
- `implementation_id`: published implementation version
- `environment`: deployment environment, currently defaulting to `production`
- `is_active`: whether this deployment is live for that environment
- `published_at`, `created_at`, `updated_at`: deployment timestamps

The runtime registry is compiled from active deployments instead of scanning raw route-definition rows on every request.

Operational notes:
- Publishing creates a new active deployment for the target environment and supersedes the previously active one.
- Unpublishing deactivates the currently active deployment for the target environment without deleting the deployment row or the underlying `RouteImplementation`.
- Once a route has entered the live-runtime lifecycle, removing the last active deployment also removes that route from runtime-managed public surfaces such as OpenAPI, `/api/reference.json`, and legacy fallback dispatch until it is republished.

## Connection
Represents a reusable connector configuration for future live steps such as outbound HTTP or Postgres access.

Fields:
- `id`: integer primary key
- `project`: lightweight project scope label, currently defaulting to `default`
- `environment`: lightweight environment scope label, currently defaulting to `production`
- `name`: admin-facing connection label, unique within one `project` + `environment` scope
- `connector_type`: `http` or `postgres`
- `description`: optional operator note
- `config`: connector configuration payload; `http` connections currently require `base_url` and may also carry shared headers/timeouts, while `postgres` connections currently require either a DSN or host/database/user credentials
- `is_active`: whether the connection can be referenced
- `created_at`, `updated_at`: audit timestamps

Operational notes:
- This scope metadata is intentionally lighter than a full Project model; it exists to organize shared connections in the admin UI and to make route/environment intent visible while the broader multi-project roadmap remains separate.
- Flow nodes still bind saved connections by explicit id today, so scope helps operators manage and inspect records without changing runtime resolution behavior automatically.

## ExecutionRun
Represents one live runtime attempt for a deployed route.

Fields:
- `id`: integer primary key
- `route_id`, `deployment_id`, `implementation_id`: links back to the active route objects
- `environment`: environment name
- `method`, `path`: executed route signature
- `status`: `success`, `validation_error`, or `error`
- `request_data`: redaction-safe request metadata captured for the run
- `response_status_code`, `response_body`, `error_message`: execution result metadata
- `started_at`, `completed_at`: run timestamps

## ExecutionStep
Represents a per-node trace record for one `ExecutionRun`.

Fields:
- `id`: integer primary key
- `run_id`: parent execution run
- `node_id`, `node_type`, `order_index`: flow node identity and ordering
- `status`: step result status
- `input_data`, `output_data`, `error_message`: redaction-safe execution details
- `started_at`, `completed_at`: trace timestamps

## Preview/examples generation
The system still generates preview/example responses directly from `response_schema`.

Supported internal schema extensions:
- `x-mock.mode`: `generate`, `mocking`, or `fixed`
- `x-mock.type`: optional semantic value type such as `id`, `email`, `name`, `first_name`, `price`, or `long_text`
- `x-mock.generator`: legacy alias for `x-mock.type`, still accepted for compatibility
- `x-mock.options`: generator-specific settings
- `x-mock.value`: literal JSON subtree returned when the node is fixed
- `x-mock.template`: optional response-string template rendered after the node's base value is generated, with access to `value`, `request.path.*`, `request.query.*`, and `request.body.*`
- `x-builder.order`: object property order used by the drag-and-drop builder

Random generation respects standard JSON Schema keywords where useful:
- `enum`
- `format`
- `minimum` / `maximum`
- `minLength` / `maxLength`
- `minItems` / `maxItems`

For string identifiers, `format: uuid` is treated as the semantic `id` value type during normalization and sample generation.

Mode behavior:
- `generate`: type-correct true random values.
- `mocking`: type-correct values with a sharper Artificer tone, such as snarkier text, cheekier slugs/emails, sardonic company names, or longer quote/message copy that can gently roast the consumer.
- `fixed`: static literal JSON returned exactly as configured.
- If `x-mock.template` is present on a response `string` node, the node's base generated/fixed value is exposed as `{{value}}` and then wrapped with request-aware template tokens before the final string is returned.

## Request contract
`request_schema` now carries both request-body and request-parameter authoring state.
- The root object is the JSON Schema used for the request body on `POST` / `PUT` / `PATCH` routes.
- Optional `request_schema["x-request"]["path"]` and `request_schema["x-request"]["query"]` sections store flat object schemas for path and query parameters.
- Path parameter names are derived from the saved route path (for example `/api/devices/{deviceId}`) and are automatically kept required/in-order to match the live route template.
- If a route placeholder exists before explicit path-parameter metadata is authored, OpenAPI still publishes that parameter as a required `string` path input by default.
- Query parameters use the same object-schema shape, with `required` and `x-builder.order` preserving UI state.
- Parameter authoring is intentionally limited to flat scalar/enum fields today; nested parameter objects, arrays, and advanced serialization styles are not modeled yet.

## Catalog bundle
The admin import/export flow still uses a native Artificer JSON bundle for backup and environment sync.
- Top-level bundle fields are `schema_version`, `product`, `exported_at`, and `endpoints`.
- Each bundled endpoint stores the editable route contract, including request/response schemas and runtime simulation settings, but excludes DB-only fields such as `id`, `created_at`, and `updated_at`.
- V1 imports match existing routes by normalized `method + path`; `slug` remains an internal field that can be de-duplicated during import.
- Supported import modes are `create_only`, `upsert`, and `replace_all`, with dry-run previews available before any changes are applied.
- Confirmed route deletion, including route removal triggered by `replace_all`, explicitly clears `ExecutionStep`, `ExecutionRun`, `RouteDeployment`, and `RouteImplementation` rows before deleting the `EndpointDefinition`.

## AdminUser
Represents a dashboard user who can sign into the private admin UI and API.

Fields:
- `id`: integer primary key
- `username`: unique sign-in identifier
- `full_name`: optional display name used in the admin UI
- `email`: optional unique contact/login-recovery address for admin operations
- `avatar_url`: optional custom profile image URL used in the admin UI
- `password_hash`: stored password hash
- `is_active`: whether the account can sign in
- `role`: `viewer`, `editor`, or `superuser`
- `is_superuser`: compatibility flag now derived from the role model in practice
- `failed_login_attempts`: rolling failed-login counter used for brute-force protection
- `last_failed_login_at`: timestamp of the last failed login attempt
- `locked_until`: temporary lockout deadline after too many failed logins
- `must_change_password`: whether the account is blocked on password rotation
- `last_login_at`, `password_changed_at`: security audit timestamps
- `created_at`, `updated_at`: audit timestamps

Role behavior:
- `viewer`: can browse the route catalog and use preview tools
- `editor`: viewer permissions plus route/settings/schema mutations, flow/deployment scaffolding, and route import
- `superuser`: editor permissions plus admin-user management
- Repeated failed sign-ins can temporarily lock an account, and the API also applies a client-IP throttle before password verification continues.

Related admin endpoints:
- `GET /api/admin/account/me`: returns the signed-in admin user's profile details
- `PUT /api/admin/account/me`: updates the signed-in admin user's own account profile fields, currently `username`, `full_name`, `email`, and `avatar_url`
- `POST /api/admin/account/change-password`: rotates the signed-in admin user's password and clears `must_change_password`
- `GET /api/admin/users`: lists all admin users for superuser management
- `GET /api/admin/users/{id}`: reads a specific admin user for superuser management
- `POST /api/admin/users`: creates an admin user, including profile details and role/access flags
- `PUT /api/admin/users/{id}`: updates an admin user, including profile details, password resets, and access flags
- `DELETE /api/admin/users/{id}`: deletes an admin user and revokes any historical sessions tied to that account

Response shape notes:
- `AdminUserRead` now exposes the stored `avatar_url` plus a derived `gravatar_url`, so the frontend can show a consistent avatar even when no custom image has been configured yet.

## OpenAPI model
The OpenAPI schema is generated dynamically by mapping `EndpointDefinition` fields to OpenAPI path entries.
- Public OpenAPI only includes routes selected by the shared public-route policy: enabled legacy routes with no runtime records yet, plus runtime-managed routes that currently have an active deployment.
- The root `request_schema` body becomes `requestBody` for `POST` / `PUT` / `PATCH` after stripping internal request-parameter metadata.
- `request_schema["x-request"]["path"]` and `request_schema["x-request"]["query"]` become OpenAPI `parameters`.
- `response_schema` becomes response schema after stripping `x-mock` (including template metadata) and `x-builder`.
- `summary` and `description` are used in the OpenAPI operation.

## Public reference feed
The public `/api/reference.json` feed exposes sanitized route metadata for the `/status` page quick reference.
- The same shared public-route policy gates which routes appear there, so runtime-managed routes disappear from the feed unless they still have an active deployment.
- Each published route now also carries a computed `publication_status` payload so the status page can show whether a route is deployment-backed live or still on the legacy mock path without hard-coding those labels in the browser.
- `request_schema` and `response_schema` are stripped of internal `x-mock`, `x-builder`, and `x-request` keys before publishing.
- `sample_response` is generated from `response_schema`.
- `sample_request` is generated from the root request-body schema for `POST` / `PUT` / `PATCH` routes so the public examples modal can show the JSON body to send alongside the mock response.

## System health endpoint
`/api/health` is now a system-owned health surface rather than a DB-authored route.
- The response reports an overall status plus per-dependency checks for the API process, database, deployment registry, public reference generation, and OpenAPI generation.
- `/api/health` is reserved and cannot be claimed by user-authored route definitions.

## Boundary rules

These rules are part of the intended architecture and should remain true:
- Public OpenAPI should be derived from route contracts, not from flow-node internals.
- Live implementations should be stored in `flow_definition`, not mixed into `response_schema` or `x-mock`.
- Preview/example generation can remain schema-driven even when deployed runtime behavior moves to the live flow engine.
- Once a route has entered the live-runtime lifecycle, it should not remain publicly reachable or documented through the legacy enabled-route path unless it still has an active deployment.
- Connectors and secrets belong to live implementations and deployments, not to public contract documents.
