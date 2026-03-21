# Admin UI

The admin UI is a Vue + Vite + Vuetify application that lets users manage routes, contracts, live implementations, and deployments.

## Key screens
- **Login**: Dedicated sign-in screen for admin users, with concise route-focused copy, explicit remember-me behavior, and bootstrap-password guidance for fresh installs.
- **Login hardening**: The admin login route now rate-limits by client IP, temporarily locks individual accounts after repeated failures, and writes failed/blocked/successful sign-in events to the backend logs.
- **Catalog + settings**: Browse the live catalog, search/filter routes, export/import the full route bundle, review live telemetry summaries for recent runtime traffic, and edit endpoint identity/runtime behavior without competing against the schema canvas. When a route is selected, the catalog rail can collapse so the workspace gets more horizontal room.
- **Route workspace tabs**: Existing routes now open inside a route-first workspace split into `Overview`, `Contract`, `Flow`, `Test`, and `Deploy`.
- **Profile**: Dedicated self-service account page for the signed-in admin user, including account summary, full-name/email/username/profile-image updates, permission visibility, and password rotation.
- **Users**: Separate superuser-only user-management page that treats the directory as the primary surface, adds summary cards plus search/filter controls, opens account creation in a dedicated dialog, and supports creating, editing, disabling, and deleting admin accounts with optional profile-image URLs plus activity metadata such as last sign-in and account creation time.
- **Route form**: Route tags are authored through a chip-style tag box with removable pills instead of a plain comma-separated text field, and the form no longer exposes the internal `slug` field.
- **Contract authoring**: The route `Contract` tab now embeds the request/response builder, with a compact add-tools rail, separate field/value palettes, a connected pill-tree canvas with dedicated drag handles, collapsible object/array branches, inline row anchors plus end-of-branch add targets, plus-button insert menus as a click alternative to drag/drop, adjacent below-canvas field settings and preview-input panels, import/copy actions, response-side route-value pills derived from saved path and query definitions, response-string template controls plus helper chips in the inspector, and a request-side split between `JSON body`, `Path params`, and `Query params` authoring. Row icons now carry the field data type without a second adjacent type badge. The current tree surface is still considered transitional as the roadmap pivots toward a `Vue Flow`-backed canvas architecture.
- **Flow**: The `Flow` tab now uses a Vue Flow canvas for `flow_definition`, with an API-only trigger entry, fixed-size nodes, visible `True` / `False` / `Case` / `Default` ports, drag-to-canvas palette actions, explicit `Error Response` terminals, a separate selected-node inspector, compact route-scoped connector context (counts/scope/refresh) plus a direct link to the dedicated `Connectors` page, and a canvas-native full-editor mode that keeps the graph primary by default through compact floating add/info/node launchers, a top-center control bar, a MiniMap, and node-local quick actions while preserving the same backend data model.
- **Connectors**: Dedicated top-level page for shared HTTP/Postgres connector credentials and metadata, including create/edit, retire/reactivate, and delete (with in-use protection errors when referenced by saved flow implementations).
- **Test**: Route testing is now split between schema-driven preview tools and execution-history visibility for published live routes.
- **Deploy**: The `Deploy` tab publishes the current implementation into the runtime registry and shows deployment history.

## API contract
The frontend communicates with the backend via the admin API under `/api/admin`.
- `POST /api/admin/auth/login`
- `GET /api/admin/auth/me`
- `POST /api/admin/auth/logout`
- `GET /api/admin/account/me`
- `PUT /api/admin/account/me`
- `POST /api/admin/account/change-password`
- `GET /api/admin/users`
- `GET /api/admin/users/{id}`
- `POST /api/admin/users`
- `PUT /api/admin/users/{id}`
- `DELETE /api/admin/users/{id}`
- `GET /api/admin/endpoints`
- `GET /api/admin/endpoints/export`
- `POST /api/admin/endpoints/import`
- `GET /api/admin/endpoints/{id}`
- `POST /api/admin/endpoints`
- `PUT /api/admin/endpoints/{id}`
- `DELETE /api/admin/endpoints/{id}`
- `GET /api/admin/endpoints/{id}/implementation/current`
- `PUT /api/admin/endpoints/{id}/implementation/current`
- `GET /api/admin/endpoints/{id}/deployments`
- `POST /api/admin/endpoints/{id}/deployments/publish`
- `GET /api/admin/connections`
- `POST /api/admin/connections`
- `PUT /api/admin/connections/{id}`
- `DELETE /api/admin/connections/{id}`
- `GET /api/admin/executions`
- `GET /api/admin/executions/{id}`
- `GET /api/admin/telemetry/executions`
- `POST /api/admin/endpoints/preview-response`

The preview endpoint accepts a response schema plus optional path params, query params, request body JSON, and `seed_key`, which lets the schema studio render request-aware template tokens without calling the public route for every edit.

## UX notes
- Logged-out users should only see the sign-in journey; catalog/editor/preview/profile/user-management controls should stay hidden until authentication succeeds.
- Active sessions live in browser `sessionStorage`; remember-me additionally copies a bearer session token to `localStorage` so reloads and restarts can restore the session without persisting the raw password.
- New bootstrap or reset passwords must be rotated through the dedicated profile screen before endpoint CRUD or user-management routes unlock.
- Admin RBAC now uses explicit roles: `viewer` can browse routes and run previews, `editor` can also create/edit/delete/import routes and schemas, and `superuser` additionally manages dashboard users.
- The top bar should behave like a conventional app shell: keep brand, primary nav, theme control, and the username-plus-avatar account menu in the header, while routed pages carry their own titles and supporting copy in the content area.
- The admin shell now uses the Artificer dark/light themes with a dark-first obsidian-and-neon palette; keep new surfaces consistent with that hierarchy rather than introducing a second visual language.
- Direct nav should stay reserved for high-frequency product surfaces such as `Routes` and superuser-only `Users`, while personal actions such as `Profile` and `Sign out` stay in the account dropdown.
- Account avatars should prefer the admin user's configured profile image URL and fall back to Gravatar when no custom image has been set yet.
- The `Users` page should stay directory-first: use one clear primary `New user` action, keep search/filter tools near the directory table, and push add/edit account details into dialogs rather than leaving a large create form permanently open beside the list.
- The route `Overview` and `Contract` tabs should stay distinct inside the route workspace so route metadata/defaults edits do not crowd the contract-authoring flow.
- The route-first workspace tabs are now the primary mental model; future UI work should deepen those tabs rather than re-flattening route editing back into one undifferentiated page.
- The `Flow` tab should stay focused on API data moving through the system: one fixed `API Trigger`, then logic, transform, connector, and response nodes. The graph should make branches explicit on-canvas instead of hiding them in inspector-only configuration, the full-editor mode should feel like one canvas workspace instead of a magnified page form, and its secondary tooling should stay opt-in so the canvas is not buried under permanently expanded panels. Follow-up UX work should improve mapping visibility and sample data rather than add alternate trigger families yet.
- The fixed top bar should own the full top edge of the admin app; desktop scrolling should happen inside the main content shell so the scrollbar starts below the header instead of beside it.
- Navigating between major admin surfaces should reset the main content shell back to the top, so routes like the preview flow or legacy schema redirects do not inherit a half-scrolled workspace from the previous page.
- The endpoint catalog/settings workspace should keep the left rail and top-level shell mounted while switching between browse/create/edit records, leaving the visible transition scoped to the right-hand record pane. The catalog rail may collapse after a route selection, but reopening it should preserve filters and scroll state.
- On desktop, the endpoint catalog rail should act like a bounded navigator with its own vertical scroll region and client-side pagination so long catalogs do not push the main editor down the page.
- Read-only roles should not see create, duplicate, schema-edit, import, or destructive route actions in the UI, and the router should redirect them away from write-only admin surfaces instead of letting them discover the restriction only after an API 403.
- The desktop endpoint workspace should let the catalog card fill the full left rail, pin that rail within the main content shell, and leave the right-hand settings pane on the main content scroll while the catalog list keeps its own internal scroll region.
- Endpoint list cards should stay compact and scannable: clear method badge, strong route name, one-line route/category metadata, and a balanced horizontal live-state/action cluster with enough breathing room to stay easy to scan.
- Route-catalog import/export should live on the browse surface: export downloads the native Artificer bundle directly, while import opens a dialog that accepts a file or pasted JSON, previews `create` / `update` / `delete` / `skip` / `error` operations, and only applies changes after the user confirms.
- Disabled route badges should use the error palette consistently in route headers, preview headers, and list rows so a non-live route cannot masquerade as a neutral state.
- The desktop schema studio should keep a compact builder-tools rail on the left, keep the field settings and preview-input forms adjacent under the canvas in the middle column, and let the preview rail stay focused on generated output.
- The desktop schema studio should bias space toward the canvas rather than giving the preview rail equal visual weight, so authoring remains the dominant task on wide screens.
- The schema-studio roadmap is now canvas-first: the route `Flow` tab provides the first Vue Flow-based reference surface, and future schema-editor work should preserve the current schema/inspector/preview workflow while deciding how much canvas-style composition actually improves JSON Schema authoring.
- The builder palette should separate structure from scalar semantics: node pills target the key rail, while response-only behavior and value-type pills target the scalar value lane.
- Route placeholders should surface in the response editor as draggable route-value pills, so scalar response fields can echo live URL segments without pretending those values belong to the request JSON body.
- Request authoring should keep path/query inputs distinct from the JSON body: path parameter names come from the saved route template, query parameters are edited as a flat list of scalar fields, and the request body builder continues to own only JSON payload shape.
- Linking a route-value pill should preserve the selected scalar field's existing type and JSON Schema constraints, so the saved response contract and generated OpenAPI stay aligned while runtime previews coerce the incoming path segment.
- Response-side route-value pills should follow the current request-path parameter definitions closely enough to feel coherent: fresh links can pick up request-path type/format hints, preview samples should use request-aware defaults such as UUID-shaped IDs or clipped string samples, and duplicate linked-field length inputs stay hidden in the response inspector to avoid editing the same constraint in two places.
- Root-shape changes should live on the selected node's inspector controls rather than being duplicated in the builder palette.
- Duplicating an endpoint should open the create flow with a prefilled copy, auto-adjust the name/path, and default the duplicate to disabled so the user can review it before publishing; the backend regenerates the internal slug from the copied name.
- The schema studio is builder-first: users drag Vuetify chip pills into a tree workspace, edit node settings in the left inspector rail, and use import/copy actions only as advanced helpers.
- The canvas tree should stay visually legible at a glance: each node renders as a compact pill with a type-specific lead icon, object/array relationships stay connected by guide lines, row plus anchors sit inline with the child rail for "insert before", and branch-end plus anchors stay aligned on that same rail for "append at end" actions.
- Dragging should feel like a secondary precision action: use a dedicated drag handle, keep the node pill itself focused on selection, and show a clearer line-style drop indicator when an insert anchor is active.
- Dragging schema pills should feel like moving a pill, not like dragging a browser-clipped screenshot; custom drag ghosts should preserve the same visual language as the canvas and builder palette.
- Larger schemas should remain collapsible and scannable, especially for nested objects and arrays, so long branches can fold down without losing their place in the tree.
- Arrays in the schema studio currently describe one repeated item shape through JSON Schema `items`; the array controls should speak in terms of `Item shape`, and the array tail anchor sets or replaces that repeated item schema instead of creating tuple-style array siblings.
- Response nodes can be static, true-random, mocking-random, or linked to a saved route parameter per field; request nodes stay schema-only and intentionally omit mock controls.
- Request parameter editing is intentionally limited to flat scalar/enum path and query fields for now; the UI does not yet model nested parameter objects or advanced serialization settings.
- The response inspector exposes the currently selected behavior and semantic value type for scalar fields, while the primary canvas interaction lets users drag those semantics directly onto the value lane.
- Semantic value types should be the primary response-authoring language for scalar fields; compatible string formats and scalar type coercions should follow from that choice instead of forcing users to juggle parallel value-type and format concepts. Common auth/demo fields such as `Username` and `Password` should live directly in that palette instead of being hidden behind generic text.
- The response builder uses the authenticated preview API for live sample payloads, keeps `seed_key` controls in the live-preview panel itself, and only shows the manual regenerate action when no `seed_key` is set; request mode reuses that right rail as a live schema preview so the studio keeps a stable three-panel rhythm.
- Response-string fields can optionally layer a template over their generated base value from the inspector; helper chips should cover `{{value}}` plus current path/query/body token suggestions, and the matching request-context inputs should stay close to the canvas so the live preview pane keeps room for the sample output itself.
- Alerts in the schema journey should be dismissible, and the primary `Save schema` action should only enable once the current route schema is actually dirty.
- Canvas selection should always drive the inspector directly; nested node clicks must update the active inspector target instead of bubbling back up to parent containers.
- The dedicated route-preview screen hits the public route directly so runtime behavior matches the backend dispatcher, appending only non-empty query parameters after resolving the configured path placeholders; schema-studio response preview still uses the authenticated preview API for fast editor feedback.
- The `Test` tab should increasingly become the home for live execution visibility, while schema preview remains contract-oriented tooling.
- The `/endpoints` browse mode should use its empty-space summary area for operational context such as route mix and recent live telemetry, not just create/import actions.
- Validation runs both in the browser for basic field checks and in the backend when saving.
- The public/API/admin shells now serve baseline security headers (`CSP`, `X-Frame-Options`, `X-Content-Type-Options`, and `Referrer-Policy`), with HSTS added automatically on HTTPS API responses and in the runtime Nginx config.
- Use skeleton states during session restore and initial catalog/editor loads to keep state transitions visually stable.
- Prefer Vuetify components wherever possible to keep styling, states, and interaction affordances consistent across the admin journey.
- Follow Vuetify's density guidance by defaulting interactive admin controls toward `compact` density unless a specific control needs more room for readability.
