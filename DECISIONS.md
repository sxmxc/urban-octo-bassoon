# DECISIONS

## 2026-03-19: Local browser QA should reuse the running stack and dedicated QA accounts
- **Stack verification**: Before browser-driven verification, check whether the local Compose stack is already serving the app via `docker compose ps --format json`, `http://localhost:3000`, and `http://localhost:8000/api/health` instead of blindly rerunning bootstrap commands.
- **Port safety**: Reuse a healthy running stack when possible; do not bounce containers or try to reclaim the same ports just to get a fresh browser session.
- **Auth workflow**: Browser-driven QA should sign in through the normal admin login flow with a dedicated `make ui-test-user` account, keeping `editor` as the default role and using `superuser` only for superuser-only flows.

## 2026-03-18: Test surfaces must separate contract preview from live/public execution
- **Operator workflow**: Keep the route `Test` journey, but make it explicit that admin contract preview and live/public requests are two different actions with different runtime guarantees.
- **Contract boundary**: Route testers may generate schema-driven examples from `request_schema` / `response_schema` and preview inputs, but that preview path must remain admin-only and must not imply live connector or deployment execution.
- **Live-state labeling**: The workspace and dedicated tester should summarize whether a route is still on the legacy mock path, currently served by an active deployment, disabled entirely, or stuck behind draft-only runtime history with no active deployment, so operators can tell when a live request will execute runtime code versus return `404`.

## 2026-03-18: Runtime-managed routes are public only through active deployments
- **Boundary trigger**: Once a route has entered the live-runtime lifecycle by saving a `RouteImplementation` or creating a `RouteDeployment`, stop treating the plain enabled endpoint row as sufficient for public docs or legacy mock dispatch.
- **Public surfaces**: Use one shared backend selector for OpenAPI, `/api/reference.json`, and legacy mock fallback so runtime-managed routes disappear from those public surfaces unless they still have an active deployment.
- **Transition model**: Keep enabled routes with no runtime records on the legacy public path for now, so the repo can continue migrating route-by-route instead of forcing an all-at-once cutover.

## 2026-03-18: Unpublishing deactivates deployments instead of deleting runtime history
- **Operator workflow**: Expose an explicit admin publish/unpublish control so operators can remove a route from live traffic without editing the database directly.
- **State model**: Treat unpublish as `RouteDeployment.is_active = false` for the target environment rather than deleting `RouteDeployment` or `RouteImplementation` rows, so deployment history and draft/live implementation state remain auditable.
- **Public effect**: Because OpenAPI, `/api/reference.json`, and legacy fallback now share one public-route selector, deactivating the last active deployment immediately removes a runtime-managed route from those public surfaces until it is republished.

## 2026-03-18: Bespoke editor drag-and-drop must move onto a maintained DnD library
- **Interaction foundation**: Stop relying on native HTML5 `dragstart` / `drop` / `dataTransfer` as the primary interaction layer for bespoke editor surfaces such as the schema studio and Flow palette, because the browser-default drag model is too limited and inconsistent for the product we want.
- **Preview quality**: Require a library-backed drag overlay/preview model so copy-style drags look like intentional tool copies rather than clipped screenshots of the original DOM node.
- **Capability bar**: The chosen library must support custom drag previews, explicit copy-vs-move semantics, richer drop-state hooks, and enough extensibility to power both today's schema/tree interactions and the Flow editor's palette-to-canvas workflows.

## 2026-03-18: Flow focus-mode tools should default to compact launchers
- **Workspace rhythm**: In Flow focus mode, keep the canvas visually primary by defaulting add-node, flow-info, and selected-node tools to small floating launchers instead of leaving every overlay expanded all the time.
- **Debug surfaces**: Treat route paths and designer JSON as secondary debugging surfaces behind a flow-info popover rather than a permanent bottom-center slab, so graph scanning stays readable on normal desktop heights.
- **Inspector behavior**: Let node selection open the inspector on demand and keep a small selected-node launcher visible even when the dock is hidden, so detail editing stays one click away without monopolizing the canvas.

## 2026-03-18: Flow full-editor should be canvas-native
- **Workspace model**: Treat Flow focus mode as a dedicated in-canvas workspace that preserves the admin top bar and moves palette, diagnostics, and editing chrome into floating overlays instead of stretching the default page layout to fill more space.
- **Vue Flow add-ons**: Lean on Vue Flow's supplemental UI where it directly improves workflow scanning and manipulation: floating `Controls` for viewport actions, `MiniMap` for spatial awareness, and `NodeToolbar` for node-local quick actions.
- **Node ergonomics**: Keep workflow nodes fixed-size for scanability and use the floating inspector plus node-local quick actions for editing, rather than reintroducing expanding node cards on the graph.

## 2026-03-18: Flow editor affordances must stay explicit
- **Canvas behavior**: Keep flow nodes fixed-size on the graph and move detailed editing into the inspector, because node expansion on selection made layout and branch scanning less predictable.
- **Branch behavior**: Surface `If` and `Switch` routing directly through visible canvas ports (`True`, `False`, `Case`, `Default`) plus path labels, instead of relying on inspector-only branch metadata to explain how a graph connects.
- **Terminal behavior**: Treat `error_response` as a real terminal path for both validation failures and explicit branch exits, while still keeping `set_response` as the primary success terminal.
- **Editor mode**: Provide a browser-page full-editor mode for Flow with palette, canvas, controls, and inspector intact, rather than overloading the canvas fit/center control with a fullscreen expectation.

## 2026-03-18: API-first branching flow model
- **Trigger model**: Keep `api_trigger` as the only entry node for now even while borrowing workflow UX ideas from n8n, so the product stays route-first instead of drifting into a generic automation builder.
- **Logic model**: Introduce first-class `if_condition` and `switch` nodes on top of the existing connector/transform/response nodes, and make branch routing explicit on flow edges instead of hiding it in node-specific runtime behavior.
- **Graph model**: Move the live runtime and Flow validator from a single linear path assumption to an acyclic branch-aware graph model, while still requiring every reachable branch to eventually resolve into `set_response` or an explicit `error_response` terminal.

## 2026-03-18: First live connector execution model
- **Node model**: Expand the live runtime with typed `http_request` and `postgres_query` flow nodes instead of overloading `transform` or `x-mock`, so outbound integrations remain explicit in `flow_definition` and keep the public contract boundary intact.
- **Connection model**: Keep connector secrets/config on shared `Connection` records, require flow nodes to reference those saved connections by id, and let the Flow inspector bind nodes to those records rather than embedding connection credentials directly in the graph.
- **Safety model**: Keep the first connector slice synchronous and bounded, using shared HTTP base URLs plus read-only parameterized Postgres queries, while recording summarized execution traces and continuing to reserve arbitrary user code execution for a later milestone.

## 2026-03-14: Project bootstrap decisions
- **Tech stack**: FastAPI + SQLModel + Alembic for backend; the frontend started on React + Vite before later moving to Vue + Vuetify.
- **Persistence**: Postgres is the single source of truth for endpoint definitions.
- **OpenAPI**: Live generation on each request from DB-backed endpoint definitions.
- **Admin auth**: Basic username/password for v1.
- **Data format**: Use JSON Schema for request/response schemas; responses will be generated from templates.

## 2026-03-14: Local Docker bootstrap reliability
- **Startup scripts**: Invoke container startup scripts through `sh` so bind-mounted checkouts do not depend on host executable bits.
- **Postgres image**: Use the Debian-based Postgres image for local development to avoid Alpine locale bootstrap warnings.
- **Health checks/auth**: Probe the configured app database and initialize Postgres with password-based local and host auth to avoid misleading readiness failures and init warnings.
- **Frontend dev server**: Keep Vite host validation enabled by default, but make allowed hostnames and Docker proxy targets configurable through environment variables.

## 2026-03-14: Admin editor and preview strategy
- **Schema editing**: Use simple JSON textareas for request schema, response schema, and example template fields in v1 rather than introducing a heavier schema-builder abstraction.
- **Preview behavior**: Run previews against the public mock route so editor feedback stays aligned with backend path matching, response shaping, and enable/disable behavior.
- **Example templates**: Treat `example_template` as arbitrary JSON across models and schemas so endpoints can return arrays or objects without special-casing.

## 2026-03-14: Frontend auth and theme UX
- **Auth journey**: Split the frontend into a dedicated logged-out sign-in route and protected editor routes so catalog/editor UI only appears when the user is authenticated.
- **Credential persistence**: Keep active admin sessions in `sessionStorage` by default and only copy credentials to `localStorage` when the user explicitly opts into remember-me behavior.
- **Loading states**: Use skeleton screens for session restore, catalog loading, and editor/preview hydration so transitions stay calm and informative.
- **Theming**: Persist an explicit light/dark theme toggle on the client rather than relying only on system defaults.

## 2026-03-14: Unified schema builder and mock generation
- **Response contract**: Replace `example_template` and `response_mode` with a single `response_schema` contract that stores generation and fixed-value behavior in `x-mock` extensions, while `x-builder.order` preserves drag/drop property order.
- **Authoring UX**: Replace raw JSON textareas with a tree-based drag-and-drop schema builder that uses a palette, nested workspace, inspector, and live generated preview.
- **Preview flow**: Add an authenticated `POST /api/admin/endpoints/preview-response` route so the editor can request generated samples without depending on public route calls for every keystroke.
- **OpenAPI publishing**: Strip internal builder/generator extensions from public OpenAPI output so the published spec remains clean JSON Schema.

## 2026-03-14: Backend bootstrap and migration path
- **Startup bootstrap**: Run `alembic upgrade head` during API startup and seeding instead of `SQLModel.create_all()`.
- **Migration strategy**: Keep Alembic config and revisions under `apps/api/migrations/` so they are available inside the API Docker build context and can migrate legacy endpoint rows in-place.

## 2026-03-15: Frontend pivot to Vue + Vuetify
- **Frontend stack**: Replace the React admin app with Vue 3 + Vuetify so the project can lean on a coherent component system instead of custom one-off styling.
- **Schema journey**: Split endpoint settings and schema editing into separate routes so the schema builder has a dedicated full-page canvas, inspector, and preview surface.
- **Vuetify-first UI**: Prefer Vuetify components wherever possible, including draggable `v-chip` palette pills, cards, tabs, alerts, skeletons, and form controls.
- **`@vuetify/v0` usage**: Use `createStorage` and `createTheme` from `@vuetify/v0` to manage the persisted light/dark theme toggle alongside Vuetify's runtime theme.
- **MCP setup**: Commit a repo-level Vuetify MCP config and frontend package scripts so AI-assisted contributors can connect to the official Vuetify MCP server without re-discovering the setup.

## 2026-03-15: Admin endpoint duplication workflow
- **Duplicate UX**: Launch duplication into the existing create-route form rather than immediately persisting a second record, so operators can review and tweak the copy before it exists in the catalog.
- **Safety defaults**: Auto-adjust the duplicated endpoint's name, slug, and path, and default the copy to disabled so a quick duplicate cannot accidentally shadow an existing public route.

## 2026-03-15: Admin catalog rail behavior
- **Rail ergonomics**: Treat the endpoint catalog as a bounded navigation rail on desktop, with its own vertical scroll area, rather than letting long lists extend the whole page.
- **Pagination scope**: Keep catalog pagination client-side after filtering so the rail stays lightweight while the backend remains focused on endpoint CRUD and runtime concerns.

## 2026-03-15: GitHub repository rename to Mockingbird
- **Canonical repo slug**: Treat `sxmxc/mockingbird` as the source-of-truth GitHub repository and update local git remotes plus deploy/docs references accordingly.
- **Published image names**: Because runtime image names follow `ghcr.io/<owner>/<repo>-<image>`, the documented GHCR targets now resolve to `ghcr.io/sxmxc/mockingbird-api` and `ghcr.io/sxmxc/mockingbird-admin-web`.

## 2026-03-15: CI smoke-test env bootstrap
- **Workflow bootstrap**: Have the Docker smoke test create `.env` from `.env.example` before running Compose so CI behaves like a clean developer checkout without depending on ignored local files.

## 2026-03-15: Mockingbird public surface and brand
- **Product name**: Present the system publicly as Mockingbird, including a shared mascot SVG used as the primary logo/favicon in the admin shell and public API landing page.
- **Public homepage**: Add a branded landing page at `/` and `/api` plus a live `/api/reference.json` feed so the public API has a human-friendly homepage that stays aligned with the DB-backed catalog.
- **Generator modes**: Extend response generation to support three authoring modes per node: fixed/static, true random, and mocking-random.
- **Docker/frontend isolation**: Keep the frontend container's dependency tree isolated in Docker-managed volumes and refresh it automatically from `package-lock.json` changes instead of depending on host `node_modules`.

## 2026-03-15: Public hero artwork and semantic mock value types
- **Landing hero direction**: Treat the top of the public site as a full-viewport hero and keep the copy editorial and minimal rather than explaining the reveal mechanic in-product.
- **Artwork workflow**: Prefer explicit `hero-top.*` and `hero-bottom.*` assets from `apps/api/static/landing/` so the public hero can fade between two fixed frames, while keeping a single tall `hero.*` asset as a fallback.
- **Hero motion**: Use the hero scroll progress to drive an eased crossfade between top and bottom artwork frames rather than vertically sliding the same image through the viewport.
- **Mock semantics**: Store an explicit `x-mock.type` for generated and mocking fields, using human-friendly value types such as `id`, `name`, `first_name`, `email`, and `price`, while still accepting legacy `x-mock.generator` aliases.
- **Legacy compatibility**: Normalize stored response schemas before runtime sample generation so older rows using short `text` generators on quote/message-style fields can inherit the newer `long_text` behavior without requiring an immediate manual reseed.

## 2026-03-15: Backend session lifecycle stability
- **Session management**: Use a yielded FastAPI session dependency backed by a shared `session_scope()` context manager so every request reliably returns its SQLAlchemy connection to the pool.
- **Direct callers**: Non-request code such as OpenAPI generation should use the shared context manager rather than reaching through the dependency function.

## 2026-03-15: Public quick reference UX
- **Reference layout**: Present the public endpoint catalog as a compact paginated table rather than large cards so the homepage can scan like a real API directory.
- **Examples and theming**: Keep example payloads behind an explicit modal action and persist a lightweight client-side light/dark mode toggle for the public surface.
- **Styling framework**: Use Bulma for the public homepage controls and table/modal primitives, while keeping custom CSS only for the branded hero artwork, theming, and sticky-table behavior.
- **Bulma discipline**: Favor near-stock Bulma table, modal, tag, button, and form treatments instead of layering bespoke chrome over those components.

## 2026-03-15: Public request/response examples for body routes
- **Reference payload contract**: Extend `/api/reference.json` with generated `sample_request` values for `POST` / `PUT` / `PATCH` endpoints, while keeping read-only routes response-only.
- **Landing-page modal**: Reuse the existing example modal and render request and response sections together for body-based routes so public users can see both the JSON to send and the mock payload they should expect back.

## 2026-03-15: CI/CD image and workflow strategy
- **Workflow split**: Keep a fast CI workflow for backend tests, frontend lint/test/build, and Docker Compose smoke coverage, and a separate image workflow for runtime-image validation and registry publishing.
- **Docker targets**: Preserve hot-reload local development through `dev` image targets in Compose, but publish dedicated `runtime` targets so release images do not ship Vite dev servers or `uvicorn --reload`.
- **Registry/release model**: Publish API and admin images to GHCR as multi-arch `linux/amd64` and `linux/arm64` manifests. Treat `vX.Y.Z` git tags as official releases that emit semver tags plus `latest`, while default-branch builds emit branch, `edge`, and `sha-*` tags.
- **Artifacts and provenance**: Upload per-image metadata artifacts (image name, version, digest, tags, build metadata/manifest) and attach provenance/SBOM data so CI/CD outputs are inspectable and easier to trust.
- **Standalone deploy example**: Keep a separate GHCR-backed Compose example for environments without a local checkout, and default that example to `edge` for convenience while recommending explicit release tags for real deployments.

## 2026-03-15: Runtime and dependency refresh
- **Workflow runtime**: Move GitHub Actions onto the current Node 24 JavaScript-action runtime path, upgrade the action majors accordingly, and explicitly opt workflows into `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true` so the repo catches compatibility regressions before GitHub flips the default.
- **Supported runtimes**: Standardize the project on Node 24 and Python 3.12 across Dockerfiles, CI, and local version files so contributors are less likely to drift onto stale or mismatched runtimes.
- **Security baseline**: Upgrade the backend to the current FastAPI/Pydantic/SQLModel line and the frontend to Vite 8 so the repo clears the audited Starlette/Black and Vite/esbuild advisories.
- **Frontend linting**: Move the admin app to ESLint flat config so the repo can run ESLint 10 with the current Vue parser/plugin line and stop printing deprecated-package notices during `npm ci`.
- **Transitive override**: Override `js-beautify`'s `glob` dependency to a current non-deprecated major because that package is only used through frontend test tooling and the older line was still emitting install-time deprecation warnings.

## 2026-03-15: Feature-branch and PR-driven release workflow
- **Working branch policy**: Do feature work on named `feature/*` or other task-specific working branches rather than committing directly to `main`.
- **Release note source**: Treat detailed pull requests as the canonical changelog input so automated releases can summarize shipped work from merged PR metadata instead of relying on direct commits to the default branch.
- **Merge discipline**: Keep `main` as the integration/release branch and prefer changes to land through reviewable PRs that describe user-facing impact, risk, and verification.

## 2026-03-15: GitHub wiki documentation strategy
- **Wiki role**: Use the GitHub wiki as a curated user/developer handbook for setup, admin usage, API behavior, deployment, and troubleshooting.
- **Canonical source**: Keep `README.md` and `docs/` in the main repository as the canonical documentation source, and derive the wiki content from those repo docs instead of maintaining a competing source of truth.
- **Content boundaries**: Exclude internal planning, agent workflow instructions, backlog management, and architecture decision logs from the wiki so the public handbook stays practical and audience-focused.

## 2026-03-15: Admin security hardening and account management
- **Admin identity model**: Replace the shared env-backed Basic Auth credential pair with DB-backed dashboard users plus bearer session tokens so multiple users can sign in without storing the raw password in the browser.
- **Bootstrap flow**: Create a one-time bootstrap superuser during DB init, generate its password when `ADMIN_BOOTSTRAP_PASSWORD` is unset, and require that bootstrap/reset password to be rotated before the rest of the admin API unlocks.
- **User management**: Add a dedicated security surface and admin API for password rotation plus superuser-controlled user creation, editing, disabling, and deletion.
- **Route separation**: Reserve `/api/admin` and other system-owned public paths such as `/api` and `/api/reference.json` so DB-defined public mock endpoints cannot collide with or impersonate private admin routes.

## 2026-03-15: Compact schema-studio workspace and focused frontend coverage
- **Builder tools rail**: Merge the schema palette and root-shape controls into one left-rail card so the canvas starts higher and the desktop workspace wastes less vertical space.
- **Preview rail**: Move the response seed key into the right preview rail and pair generated output with a JSON Schema tab so determinism controls stay adjacent to the preview instead of living in a separate card.
- **Coverage strategy**: Cover schema-studio drag/drop, response-preview auth expiry, and auth-session restore/login behavior with focused Vitest tests so the tighter builder workflow is protected without depending on fragile manual-only QA.

## 2026-03-15: Schema-studio pill tree and reorder affordances
- **Canvas form**: Present the schema canvas as a connected pill tree rather than stacked nested cards so hierarchy reads faster and the builder matches the product's more diagram-like authoring intent.
- **Insertion model**: Use compact plus-icon anchors for both "append into container" and "insert before this sibling" actions, keeping drop targets visible without dedicating large empty drop zones to every node.
- **Drag payloads**: Write explicit `dataTransfer` payloads for palette chips and node drags so real browsers can distinguish add-vs-move operations reliably, which restores row reordering on the live canvas.

## 2026-03-15: Schema-studio density and anchor layout
- **Visual density**: Favor slimmer, higher-contrast pills and a tighter canvas header so the builder reads as a designed tool rather than as oversized chips floating in spare space.
- **Tree anchors**: Keep "insert before" anchors inline with each child row and reserve dashed tail anchors for "append at end" actions, because stacked pre-row buttons made the branch rail look visually broken.
- **Desktop weighting**: Bias the 3-column studio toward the canvas on desktop by widening the middle column and trimming the preview rail so authoring remains the primary visual task.

## 2026-03-15: Schema-studio node/value palette split
- **Tool model**: Separate the builder tools into structural node pills plus response-only value-behavior and value-type pills, instead of keeping an armed-tool state or duplicating root-shape controls in the palette.
- **Canvas contract**: Treat the tree's key rail as the place for structural drops and the scalar value lane as the place for response semantics, so users can drag structure and meaning to visibly different targets.
- **Semantic authoring**: Make value types the primary scalar-semantic control, inferring compatible node coercions and string formats from the dropped value type instead of asking users to reconcile a separate format selector.

## 2026-03-16: Schema-studio drag feel and tree geometry
- **Canvas density**: Keep key pills, value pills, and branch anchors compact enough that the tree reads as one diagram instead of a stack of chunky tags.
- **Branch alignment**: Align branch-end add anchors with the row-level insertion anchors on the same rail so object tails do not look offset or broken.
- **Drag affordance**: Use custom pill-shaped drag ghosts and type-specific node icons, because the browser's default drag screenshot made the builder feel sloppy and less intentional.

## 2026-03-16: Task-first schema-studio language
- **Surface naming**: Prefer user-task terms such as `Live preview` and `Item shape` over internal layout terms like `Preview rail` when the label is visible in-product.
- **Header copy**: Use endpoint-specific context such as the route name or summary in the schema page header, and strip implementation narration that explains how the page is assembled instead of what the user is editing.
- **Array model**: Present arrays as one repeated item template, not as generic multi-child containers, so the editor's language matches the JSON Schema contract it saves.

## 2026-03-16: Route-first product language and linked path parameters
- **Route vocabulary**: Use `Routes`, `Schema`, and `Test route` consistently across the admin and public surfaces so the product speaks in terms of the user's workflow instead of internal UI architecture.
- **Path ownership**: Treat path parameters as route-owned inputs derived from the saved path template, and expose them in the response editor as route-value pills so users can echo real URL segments without recreating them in the JSON body tree.
- **OpenAPI output**: Publish path placeholders from the route path as required OpenAPI path parameters by default so the generated contract matches what the response editor and route preview already imply.

## 2026-03-16: Response value palette coverage
- **Route value links**: Store route-parameter response links in `x-mock` metadata so they survive schema save/load, work in authenticated previews, and echo actual public-route path values at runtime.
- **Credential-like strings**: Include `Username` and `Password` as first-class semantic string value types so common auth/demo payloads do not require falling back to generic text.
- **Password safety**: Make the `Password` generator emit bcrypt-style hashes rather than cleartext-looking secrets, because realistic mock payloads should still respect common production data expectations.

## 2026-03-16: Compact admin controls and explicit route-status badges
- **Density**: Default the main admin controls to Vuetify `compact` density so forms, buttons, and chips read as a denser tool rather than a roomy marketing surface.
- **Tags authoring**: Use a chip-based tag input for route tags instead of a comma-separated text field, because tags behave like discrete removable items rather than prose.
- **Disabled state**: Use the error palette for disabled route badges anywhere route status is summarized, because low-contrast neutral chips made the disabled state too easy to miss.

## 2026-03-16: Backend-only route slugs
- **User workflow**: Remove `slug` from the route settings form so users only manage the route name/path and do not have to understand an internal identifier that does not affect runtime routing.
- **Backend bookkeeping**: Keep `slug` on the backend model for seed/import/admin bookkeeping, but auto-generate and de-duplicate it from the route name during admin create/update requests.
- **Duplication flow**: Make route duplication adjust the visible name/path only; the internal slug should follow from the copied name instead of being edited directly.

## 2026-03-16: Mockingbird voice on the public site and in mocking-mode data
- **Hero tone**: Keep the public homepage headline playful and slightly irreverent, and restore the small warning callout so the landing page feels branded rather than like a generic API catalog.
- **Mocking-mode copy**: Let `mocking` generation sound sharper and more sarcastic than plain random mode, while keeping the content contract-safe, deterministic under seeds, and free of targeted abuse.

## 2026-03-16: Preview-rail JSON panes
- **Editor treatment**: Render the schema-studio sample response and JSON Schema tabs as syntax-highlighted JSON panes so they feel closer to a code viewer than plain `<pre>` text.
- **Overflow behavior**: Keep overflow scrolling inside the JSON pane itself so large sample payloads do not stretch the preview rail, while preserving code-style horizontal scrolling for long lines.
- **Copy affordance**: Keep schema-copy actions available both in the canvas header and inside the preview pane, using a clipboard fallback so copy still works in browsers where `navigator.clipboard` is unavailable.

## 2026-03-16: Local production-like runtime mode
- **Compose shape**: Use a separate `docker-compose.prod-local.yml` instead of pretending the existing dev compose has a real QA profile, because the production-like stack needs different Docker targets, commands, and the Nginx-served admin runtime.
- **Swap workflow**: Keep the same service names and named Postgres volume between dev and local runtime mode so contributors can swap from `make up` to `make up-prod-local` without losing local endpoint data.
- **Make ergonomics**: Expose the runtime smoke path through dedicated make targets (`up-prod-local`, `down-prod-local`, `build-prod-local`, `logs-prod-local`) so testing the built stack stays as easy as the normal dev workflow.

## 2026-03-16: Safe admin catalog background refresh
- **Refresh cadence**: Refresh the admin route catalog every 30 seconds while the page is visible, and also revalidate on focus/online once the last successful sync is stale, so the mounted workspace heals from out-of-band changes without requiring constant manual refreshes.
- **Draft safety**: Preserve the currently selected route record during catalog refresh whenever its settings form has unsaved edits, because blindly replacing the selected record would reset the mounted draft and lose in-progress work.
- **Failure handling**: Keep the last successful catalog rendered when refresh requests fail, and surface the refresh problem as an inline error banner instead of blanking the rail or treating a transient fetch failure like an empty catalog.

## 2026-03-17: Request-schema parameter contract
- **Contract shape**: Keep the request JSON body schema at the root of `request_schema`, and store request-parameter metadata under `request_schema["x-request"]` so older body-only routes remain valid while new path/query editors have somewhere structured to persist their data.
- **Path ownership**: Treat saved route placeholders as the source of truth for path-parameter names, automatically resyncing the stored `x-request.path` schema whenever the route path changes so parameter names cannot drift away from the live route template.
- **Publishing behavior**: Generate OpenAPI `parameters` from `x-request.path` and `x-request.query`, keep `requestBody` sourced only from the root body schema, and strip `x-request` from public request-schema/reference output so public consumers see a clean contract instead of builder metadata.

## 2026-03-17: Native endpoint catalog import/export
- **Backup format**: Use a Mockingbird-native JSON bundle with `schema_version`, `product`, `exported_at`, and serialized endpoint definitions instead of relying on raw DB dumps or OpenAPI import/export, so backups preserve the full editable route contract.
- **Identity and slugs**: Match existing routes by normalized `method + path` in v1; keep `slug` internal, include it in the bundle for bookkeeping, and regenerate/de-duplicate it on import rather than exposing it as the user-facing sync key.
- **Safety rails**: Support `create_only`, `upsert`, and `replace_all` import modes, always offer a dry-run preview, and require explicit confirmation before `replace_all` can delete routes missing from the bundle.

## 2026-03-17: Builder-first roadmap for response templating and RBAC
- **Templating direction**: Promote richer response templating into the active task list, but keep the drag-and-drop schema studio as the primary authoring surface; templating should layer onto `response_schema` / `x-mock` metadata or a node-level escape hatch instead of replacing the builder with a raw Handlebars/Liquid editor.
- **Editor safety**: Preserve the pill-tree canvas, `x-builder.order` property ordering, and the array `Item shape` mental model while designing any richer response-authoring features so power-user flexibility does not regress the current WYSIWYG workflow.
- **Access-control direction**: Prioritize role-based permissions on top of the existing dashboard-user system, because user CRUD already exists and the next gap is controlled access rather than a second user-management concept.

## 2026-03-17: Phase 1 response templating contract
- **Storage model**: Scope phase 1 templating as an optional `x-mock.template` string on response-side `string` nodes, so the existing `response_schema` tree remains the only source of response shape and OpenAPI sanitization stays centralized.
- **Rendering model**: Render templates after the normal base-value generation pass, exposing only `value`, `request.path`, `request.query`, and `request.body` context in v1; defer sibling response references, loops, and full Handlebars/Liquid logic until a later iteration.
- **Editor model**: Keep templating as an inspector-level enhancement for selected response string fields rather than introducing a second raw-template editor, which protects the schema studio's drag/drop WYSIWYG workflow, `x-builder.order`, and array `Item shape` mental model.

## 2026-03-17: Phase 1 template authoring UX
- **Inspector-first controls**: Keep response templating inside the existing response-string inspector with a `Use template` toggle, multiline field, and helper-token chips rather than adding template-specific canvas nodes or a second response editor.
- **Preview context inputs**: Let the schema-studio live-preview rail accept editable path, query, and request-body values and send them through the authenticated preview API so request-aware templates can be exercised without leaving the editor.
- **Client validation**: Mirror the backend token validation rules in the frontend before preview/save so malformed placeholders and unknown path parameters surface immediately while the user is authoring the selected field.

## 2026-03-17: Schema-studio response-authoring ergonomics
- **Column roles**: Keep the right-side live-preview column focused on generated output, and move request-context preview inputs into a full-width middle-column card beneath the canvas so the sample pane does not get squeezed off-screen.
- **Form placement**: Move selected-field settings out of the left tool rail and under the canvas, because longer inspector forms read better at canvas width and the left rail should stay dedicated to add/value palettes.
- **Editor affordances**: Show both saved path and query inputs as route-value pills where relevant, make transient editor alerts dismissible, gate `Save schema` behind a real dirty state, and use a more explicit selected-row treatment on the canvas.

## 2026-03-17: Schema-studio insertion and focus affordances
- **Insert redundancy**: Keep drag/drop as the primary structural interaction, but let the canvas plus anchors open a type menu too so users can add fields without committing to drag gestures for every small edit.
- **Detail layout**: Keep field settings and preview inputs adjacent beneath the canvas on desktop, because they are both local editing context and should not steal space from the main preview column.
- **Selection emphasis**: Prefer node-focused selection cues such as a stronger pill state and compact marker chip over full-row washes, which made the tree feel heavier and less precise.

## 2026-03-17: Schema-studio tree ergonomics follow-up
- **Drag targeting**: Treat node movement as a secondary action with its own dedicated drag handle, instead of making the whole node pill both the primary selection target and the drag source.
- **Branch management**: Allow object and array branches to collapse in-place so larger schemas stay scannable without abandoning the current tree-based mental model.
- **Inspector readability**: Group the selected-field controls into lighter sections rather than one long uninterrupted form, because the response editor is now dense enough that scan order matters.

## 2026-03-17: Schema-studio canvas architecture pivot
- **Product direction**: Treat the current pill-tree schema builder as an interim authoring surface and pivot the schema studio toward a true canvas architecture that can eventually grow beyond pure schema editing into richer route, data-source, and transform flows.
- **Library direction**: Use `Vue Flow` as the preferred foundation for the next prototype instead of layering a separate drag/drop library onto the bespoke tree, because the roadmap now values zoomable canvas composition and future graph extensibility more than incremental tree-only interaction tweaks.
- **Contract safety**: Keep the backend `request_schema` / `response_schema`, `x-builder.order`, and `x-mock` model stable during the pivot so runtime behavior, OpenAPI output, preview generation, and import/export do not change just because the frontend authoring surface evolves.

## 2026-03-17: Admin RBAC model
- **Role model**: Replace the old boolean-only admin access model with explicit `viewer`, `editor`, and `superuser` roles, while still exposing `is_superuser` in responses for compatibility during the transition.
- **Permission model**: Derive a small shared permission set from each role (`routes.read`, `routes.write`, `routes.preview`, `users.manage`) and enforce those permissions consistently in both FastAPI dependencies and the admin frontend.
- **Migration strategy**: Keep the existing dashboard-user table and session flow, add a `role` column in place, backfill legacy users from `is_superuser`, and leave the backend schema/runtime contract untouched so RBAC does not ripple into public mock behavior or OpenAPI.

## 2026-03-18: Account UX split for admin auth
- **Personal vs global admin surfaces**: Split the old all-in-one `Security` screen into a personal `Profile` route and a separate `Users` management route so self-service account work does not compete visually with superuser administration.
- **Navbar pattern**: Use a traditional account dropdown in the top bar for profile/sign-out navigation, while keeping high-frequency product surfaces like `Routes` and superuser-only `Users` visible as direct nav actions.
- **API shape**: Add dedicated `/api/admin/account/me` read/update endpoints alongside the existing password-change flow, and keep `/api/admin/users` focused on true admin-user management with a conventional read-by-id endpoint.

## 2026-03-18: Routed admin views should render a single root node
- **Transition safety**: Keep routed admin pages under a single concrete root element when they sit inside the app-level router transition, because fragment-root views can leave the shell blank during `out-in` navigation even if a hard reload works.

## 2026-03-18: Admin account polish and migration consistency
- **Account-nav pattern**: Keep the top-bar account control as a username-plus-avatar button, not a generic `Account` label, and let the dropdown hold the richer identity details; when no custom avatar is set, fall back to Gravatar so the shell still feels personal and recognizable.
- **Admin-user fields**: Treat optional `full_name`, `email`, and `avatar_url` as first-class admin-user attributes, expose them in both self-service profile editing and superuser user-management flows, and show searchable directory rows with recent account activity so the admin surface feels closer to a conventional app.
- **Alembic consistency**: Make Alembic CLI runs resolve the configured DB URL from env/settings rather than trusting the legacy SQLite value in `alembic.ini`, so manual migration commands and startup migration bootstrap always target the same database.

## 2026-03-18: Admin shell and user-management UX cleanup
- **Shell hierarchy**: Keep the fixed top bar focused on brand, primary product navigation, theme control, and the username/avatar account menu; page titles belong inside the routed page content rather than being repeated in the shell header.
- **Users workflow**: Treat the user directory as the primary `Users` screen, with one clear `New user` action that opens a dialog, because persistent side-by-side create forms made the page feel heavier and distracted from the main administration task.
- **Theme discipline**: Any custom shell/page styling should derive contrast from Vuetify theme tokens instead of hard-coded light-on-dark values, so light and dark mode stay equally legible during future UI polish passes.

## 2026-03-18: Public/admin security hardening baseline
- **Landing-page bootstrap**: Never inline live catalog JSON into executable script assignments; embed reference payloads through an escaped `application/json` script block and parse them at runtime so stored endpoint content cannot break out into executable page script.
- **Public routing**: Treat saved public paths as literal text plus explicit `{param}` placeholders, escape static segments before building match regexes, and keep the async catchall's sync DB/sample-generation work off the event loop so runtime traffic does not stall on synchronous SQLModel access.
- **Admin auth**: Add baseline brute-force protection through per-account lockouts, per-IP throttling, and audit logging of failed/blocked/successful login attempts, while keeping `/api/admin/account/me` partial updates truly partial instead of requiring `username` on every profile edit.
- **Headers**: Serve baseline browser hardening headers from both the FastAPI app and the admin runtime/dev shells, with CSP tuned separately for the public landing page, JSON API responses, and the Vite dev experience.

## 2026-03-18: Route-first platform pivot foundation
- **Product framing**: Reframe the repo, docs, and admin UI around a route-first API platform rather than a mock-only product, while keeping the existing schema-driven generator as preview/example infrastructure during the transition.
- **Data model**: Introduce first-class backend models for `RouteImplementation`, `RouteDeployment`, `Connection`, `ExecutionRun`, and `ExecutionStep` instead of overloading `EndpointDefinition` with live-runtime concerns.
- **Runtime boundary**: Make the public runtime check a compiled deployment registry first and execute only published live implementations there, while temporarily preserving a legacy mock fallback for undeployed routes so the pivot can land incrementally.
- **Admin workflow**: Keep the route workspace route-first and split it into `Overview`, `Contract`, `Flow`, `Test`, and `Deploy` tabs, even before the full Vue Flow canvas is ready.

## 2026-03-18: Image and deploy references should follow the active fork
- **GHCR example config**: Stop hardcoding the previous fork's image names in the standalone deployment example; use `IMAGE_REPOSITORY` with a current-fork default instead so renames and forks do not require editing the compose file itself.
- **Version baseline**: Align the API config, Dockerfiles, and frontend package metadata on the `1.4.0-alpha.0` line so local builds, runtime images, and OpenAPI metadata stop advertising the stale `0.1.0` default.

## 2026-03-18: Route flow editor should ship as a constrained Vue Flow canvas
- **Authoring surface**: Replace the raw `flow_definition` textarea with a Vue Flow canvas, starter-node palette, and right-side inspector while continuing to save the same backend `flow_definition` payload.
- **Initial flow shape**: Keep the first editor intentionally narrow and easy to reason about by guiding authors toward one main execution path with exactly one `api_trigger`, exactly one `set_response`, an optional unconnected `error_response`, and small starter-node validation in the browser before save.
- **Config UX**: Keep node configuration in the inspector and use small JSON sub-editors for transform output and response bodies instead of forcing either full-flow raw JSON editing or dense inline graph forms.

## 2026-03-18: Flow designer interaction model should stay canvas-first and selection-local
- **Node density**: Keep default flow nodes compact and scannable on the canvas, then let the selected node expand in place rather than making every step carry full-card weight all the time.
- **Editing locality**: Move detailed node editing beneath the canvas in a dedicated dock so the designer reads as one focused workspace, with a sticky selected step, instead of splitting attention across a permanent right rail.
- **Builder rhythm**: Favor a top toolbelt for adding steps, a large uninterrupted canvas, and a secondary signals/debug column over a three-column “palette / canvas / inspector” scaffolding layout, because the product is increasingly about live-flow composition rather than generic CRUD form filling.


*> Future decisions should append a dated entry with context and rationale.*
