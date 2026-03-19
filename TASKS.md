# TASKS

This file tracks the work needed to bootstrap and evolve the project.
Read `docs/roadmap.md` alongside this file if you are picking up the next implementation slice.

## Now
- [ ] Add execution drill-down and replay tooling on top of the new `ExecutionRun` / `ExecutionStep` records

## Next
- [ ] Move the schema editor under the route `Contract` journey instead of keeping it as a separate transitional page

## Later
- [ ] Add advanced inbound auth (API keys, bearer token policies, scopes)
- [ ] Improve OpenAPI and reference-feed publishing so only promoted runtime contracts are exposed
- [ ] Add multi-project and multi-environment support beyond the current scaffolding defaults

## Blocked
- [ ] (none)

## Done
- [x] Restrict `/api/health` migration cleanup to the legacy seeded route and keep reserved-path bundle imports as row-level import errors
- [x] Derive admin live-mode status from current deployments/implementation data instead of stale cached publication status after publish/unpublish
- [x] Sync the repository docs with backend-driven publication state, `/status` health, `/api/health`, and Swagger/ReDoc surfaces
- [x] Make route publication state and API health backend-driven across `/status`, `/api/health`, and the admin dashboard
- [x] Replace the old public landing page with a `/status` API status page and make `/` return no content
- [x] Align README and setup docs with the `/status`, `/api/health`, and Swagger/ReDoc CSP changes
- [x] Enforce immutable connector types on connection updates so API clients cannot retarget existing connection ids across HTTP/Postgres
- [x] Let Flow helper/ref pills drag and drop into JSON editors at the current cursor or selection instead of replacing the whole field payload
- [x] Add project/environment-aware connection management UI instead of the current route-level placeholder card
- [x] Add true Flow data-mapping support so operators can compose strings/objects from request and state data instead of only wiring whole refs
- [x] Add per-node input/output data-shape visibility plus pinned sample payload inspection in the Flow designer
- [x] Replace native HTML5 `dragstart` / `drop` / `dataTransfer` usage in bespoke editor surfaces with a maintained drag-and-drop library that supports drag overlays, copy/move semantics, and richer drop hooks
- [x] Fix route deletion so published routes with implementations, deployments, and executions can be removed cleanly from the UI and admin API
- [x] Preserve `make ui-test-user` helper defaults when `UI_TEST_ADMIN_*` vars are unset or blank in the shell/container env
- [x] Document the safer local browser-QA workflow around stack reuse, dedicated QA accounts, and real login
- [x] Make the `Test` journey honest about what is preview/example output versus what is draft/live runtime execution
- [x] Add an explicit route unpublish/disable-live action so operators can remove a route from the live deployment registry without deleting the route definition or draft flow
- [x] Tighten the published-runtime boundary so OpenAPI, public reference, and live dispatch can move cleanly from legacy mock fallback to deployment-backed routing
- [x] Create initial planning docs
- [x] Define project structure and high-level architecture
- [x] Scaffold backend FastAPI app and ensure it runs inside Docker
- [x] Scaffold frontend admin UI (Vite + React) and ensure it runs inside Docker
- [x] Implement core endpoint definition model + CRUD API
- [x] Implement runtime dispatch for mock endpoints driven by DB
- [x] Implement live OpenAPI generation from DB definitions
- [x] Seed initial endpoint catalog (14 endpoints)
- [x] Add baseline backend tests for bootstrap and OpenAPI generation
- [x] Stabilize Docker Compose bootstrap and startup scripts for local development
- [x] Make frontend Vite dev access configurable for remote hosts and Docker proxying
- [x] Refresh project tracking docs to match the implemented bootstrap state
- [x] Expand backend tests to cover admin CRUD endpoints and runtime dispatch behavior
- [x] Build real admin UI pages for endpoint list / edit / preview
- [x] Connect the admin UI to the backend CRUD API with basic-auth support
- [x] Add schema editor UI (JSON editor) for request/response schemas
- [x] Improve admin auth UX in the frontend (login flow, credential handling, logout)
- [x] Replace schema textareas with a drag-and-drop request/response schema builder
- [x] Add schema-driven random response generation and admin preview support
- [x] Switch backend bootstrap to Alembic migrations with legacy contract conversion
- [x] Migrate the admin UI to Vue + Vuetify with a dedicated schema editor page
- [x] Add search and filtering to the endpoint catalog
- [x] Add latency/error simulation controls to the admin settings UI
- [x] Add the public Mockingbird landing page with a live endpoint quick reference
- [x] Add mocking-style random generation alongside static and true-random schema values
- [x] Fix schema canvas selection so the inspector follows nested node clicks
- [x] Keep Dockerized frontend dependencies isolated from host `node_modules`
- [x] Refine the public landing page into a full-height hero with shared artwork hooks
- [x] Wire the public landing page to a single tall `hero` artwork asset
- [x] Add semantic mock value types so random and mocking fields stay context-aware
- [x] Refine the schema studio layout so the inspector sits in the left rail and the right rail stays preview-focused
- [x] Fix backend DB session lifecycle so request handling does not exhaust the SQLAlchemy connection pool
- [x] Rework the public quick reference into a paginated table with filters, modal examples, sticky headers, and dark mode
- [x] Simplify the public quick reference styling so it stays closer to stock Bulma
- [x] Add request-and-response examples for public POST-style endpoints in the landing-page quick reference
- [x] Add endpoint duplication support in the UI
- [x] Keep the endpoint workspace shell mounted while only the right-hand record pane transitions between records
- [x] Make the endpoint catalog rail scroll independently with client-side pagination
- [x] Update repository and deployment references after the GitHub rename to Mockingbird
- [x] Fix CI Docker smoke test bootstrap when `.env` is absent in GitHub Actions
- [x] Add a dedicated long-text value type for schema-studio string fields
- [x] Simplify the admin sign-in page with friendlier copy and a single-column intro/form flow
- [x] Stabilize GitHub Actions CI and add multi-arch image publishing for CI/CD
- [x] Add a standalone GHCR-backed Docker Compose example for image-only deployments
- [x] Audit and refresh repo runtimes, dependencies, Docker bases, and GitHub Actions versions; add README workflow badges
- [x] Remove admin-web `npm ci` deprecation warnings by migrating the lint stack to flat config and overriding the test-only `glob` path
- [x] Remove the admin workspace intro card, move desktop scrolling below the top bar, and tighten the admin left-rail behavior
- [x] Redesign the endpoint catalog cards into a denser, more scannable layout and normalize schema-studio shell scrolling
- [x] Create and populate the GitHub wiki as a curated user/developer handbook, while keeping repo docs canonical
- [x] Harden admin auth with managed dashboard users, password rotation, bearer sessions, and reserved private route validation
- [x] Fix admin-user deletion so historical admin sessions do not block account removal
- [x] Add broader frontend coverage for schema drag/drop, preview, and auth journeys, and tighten the Schema studio canvas/preview layout so it uses space more efficiently
- [x] Fix schema-canvas reordering and restyle the builder as a connected pill tree with compact plus-icon insertion targets
- [x] Give the schema studio a true UI/UX density pass with slimmer high-contrast pills, inline rail anchors, end-of-branch add targets, and a wider desktop canvas
- [x] Split schema-studio builder tools into node, value-behavior, and value-type palettes so scalar response semantics drop directly onto value lanes
- [x] Tighten schema-studio tree geometry with smaller canvas pills, aligned branch-end anchors, type-specific node icons, and custom pill drag ghosts
- [x] Re-center schema-studio copy and array authoring around user tasks by restoring `Live preview`, simplifying the page header, and labeling array edits as `Item shape`
- [x] Rewrite the admin/public product language around routes, schema, and testing; surface linked route-parameter response values and OpenAPI path parameters
- [x] Add `Username` and `Password` as semantic string value types in the response builder
- [x] Make the `Password` response value type emit password-hash strings instead of cleartext-looking secrets
- [x] Switch the route form tags input to a chip-style tag box, move the admin UI to compact Vuetify density defaults, and make disabled route badges explicitly error-colored
- [x] Stop the route-catalog search field from vertically stretching on sparse paginated pages
- [x] Hide route slugs from the admin form and auto-generate backend bookkeeping slugs from route names
- [x] Restore the public hero warning and sharpen mocking-mode copy so the landing page and generated text feel more like Mockingbird
- [x] Add syntax-highlighted, scrollable JSON panes with inline copy actions to the schema-studio live preview rail
- [x] Add a real local production-like Compose mode so a checked-out repo can swap from dev targets to runtime targets
- [x] Preserve scalar response field types and constraints when linking route-value path parameters in the schema studio
- [x] Stabilize schema-studio frontend tests so route-value pills do not collide with schema-row selectors in CI
- [x] Add background refresh and stale-catalog invalidation for the admin catalog without overwriting dirty route drafts
- [x] Expand the request builder beyond JSON bodies to path/query parameter modeling
- [x] Sync response-side route-value pills with request path-parameter definitions and hide duplicate linked-field length controls
- [x] Add full endpoint catalog export/import for backup and environment sync
- [x] Fix large-catalog import planning and preserve zero-valued request-parameter numeric constraints
- [x] Fix Postgres multi-route import flushes against the varchar-backed `auth_mode` column
- [x] Reduce or eliminate Vuetify/jsdom CSS parse noise during frontend tests
- [x] Scope schema-aware response templating so it layers onto `response_schema` without breaking the drag-and-drop WYSIWYG schema studio
- [x] Implement schema-aware response templating in backend preview/runtime flows using request path/query/body context
- [x] Add schema-studio string-template controls, helper chips, and validation for response templating
- [x] Polish the schema studio with below-canvas detail panels, query-value pills, plus-button insert menus, dedicated drag handles, branch collapse controls, dismissible alerts, dirty-only saving, and clearer selected-node cues
- [x] Expand dashboard-user management with roles and role-based access across the admin UI and admin API
- [x] Fix the admin-role Alembic backfill so existing Postgres dev databases upgrade cleanly to RBAC
- [x] Split the old security surface into dedicated profile and user-management journeys with a traditional account dropdown
- [x] Fix routes-to-profile and routes-to-schema navigation so routed transitions no longer blank the admin shell
- [x] Round out admin account/user management with profile fields, avatar support plus Gravatar fallback, directory search/activity metadata, and a migration path that keeps Alembic on the configured database
- [x] Redesign the admin shell and users page with a cleaner top bar, directory-first user management, and dialog-based account creation
- [x] Remove deprecated Vuetify theme and row-density usage surfaced by admin console warnings
- [x] Harden the public/admin surfaces against landing-page XSS, literal-path route matching, login brute forcing, missing security headers, catchall event-loop blocking, and partial profile update failures
- [x] Reframe the repo and docs around a route-first API platform instead of a mock-only product
- [x] Add backend scaffolding for route implementations, deployments, connections, execution runs, and execution steps
- [x] Add a deployment-backed live runtime path with a compiled route registry and starter flow execution engine
- [x] Add admin API scaffolding plus route-first `Overview` / `Contract` / `Flow` / `Test` / `Deploy` workspace tabs
- [x] Unblock the normal route create/edit journey by restoring visible route identity fields and save/create actions in the standard `Overview` flow
- [x] Remove hardcoded old-fork GHCR references from deploy/docs defaults and make the image-only compose example repository-configurable
- [x] Replace the raw `Flow` JSON placeholder with a real `Vue Flow`-backed live implementation editor
- [x] Expand the live runtime beyond the starter node set with first-class `HTTP Request` and read-only `Postgres Query` connectors
- [x] Add branch-aware logic nodes to the live runtime and Flow designer with first-class `If` / `Switch` support
- [x] Rework Flow-designer UX around visible branch ports, drag-to-canvas palette behavior, explicit Error Response routing, auto-arrange, and a real browser-page full-editor mode
- [x] Rebuild the Flow full-editor around floating in-canvas panels, a MiniMap, and node-local toolbars instead of stretching the old page layout
- [x] Refine the Flow full-editor into a canvas-first workspace with compact floating launchers for add-node, flow-info, and selected-node inspection
