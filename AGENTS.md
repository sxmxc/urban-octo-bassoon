# AGENTS.md

## Purpose
This repository is designed for **AI-native collaboration**. AI agents (and humans) should be able to pick up work quickly, understand constraints, and make consistent changes without breaking the core platform.

## 🧭 First things an agent must do
1. **Read these four files before making changes**:
   - `AGENTS.md` (this file)
   - `MEMORY.md` (project context and assumptions)
   - `TASKS.md` (what to work on next)
   - `DECISIONS.md` (architecture/strategy log)
2. **If the task touches architecture, runtime behavior, or product direction, also read**:
   - `docs/architecture.md`
   - `docs/roadmap.md`
   - `docs/domain-model.md`
3. Confirm the current state by checking whether the local stack is already serving the app (`docker compose ps --format json`, `http://localhost:3000`, and `http://localhost:8000/api/health`); only then run `make up` or target-specific tasks if services are missing.
4. Work in small, reviewable increments and update the tracking docs after every meaningful change.

## 🧱 Architecture Guardrails
- **Backend is the source of truth** for route contracts, route implementations, deployments, and OpenAPI generation.
- **Public contract and live implementation must stay separate**: `request_schema` / `response_schema` define the contract, while `flow_definition` defines live execution.
- **Preview/examples and deployed runtime are intentionally different paths** during the transition; do not casually intermingle them.
- **OpenAPI must reflect the published public contract**; until the publish boundary is tightened further, changes must not silently widen the drift between enabled route definitions and deployed runtime behavior.
- **Route behavior is config-driven**, not hard-coded per route.
- Keep the system **Docker-first**: running `make up` should get a developer to a usable state.

## 🎯 Current Milestone
- The repo has completed the **route-first pivot foundation**.
- The backend now has `RouteImplementation`, `RouteDeployment`, `Connection`, `ExecutionRun`, and `ExecutionStep` scaffolding plus a deployment-backed runtime registry, first-class `If` / `Switch` logic nodes, and first-class `HTTP Request` / read-only `Postgres Query` connector execution.
- The admin UI now has `Overview`, `Contract`, `Flow`, `Test`, and `Deploy` tabs.
- The `Flow` tab now uses a **Vue Flow-based implementation editor** that still saves the backend `flow_definition` contract, keeps `API Trigger` as the only entry node, and can bind logic plus HTTP/Postgres nodes to the live route graph.
- Public OpenAPI, `/api/reference.json`, and legacy mock fallback now treat routes with saved runtime history as deployment-gated; enabled legacy-only routes stay public until they enter the live runtime path.
- The admin `Deploy` tab and admin API now support explicitly disabling the live route by deactivating the active deployment without deleting the saved route definition or implementation history.
- The highest-value next steps are to fix runtime-aware route deletion, then keep improving the Flow/operator surface with connection management, data mapping, and node-shape visibility.

## 🧩 Coding Standards
- Prefer clarity over cleverness.
- Avoid large abstractions early; make them when duplication becomes burdensome.
- Write tests for any behavior that might regress (CRUD, dispatch, OpenAPI sync).
- Keep business logic in the backend; frontend should remain UI + API wiring.

## 🧭 Backend Conventions
- Use FastAPI with SQLModel for schema + DB models.
- Put most logic under `apps/api/app/` (e.g., `models/`, `services/`, `routes/`).
- Use Alembic for migrations; keep migration config and revisions under `apps/api/migrations/`.
- Any change that affects the runtime contract (endpoints, schemas, auth) must update docs.
- Keep runtime logic concentrated in services such as `app/services/route_runtime.py` rather than spreading it through route handlers.

## 🧭 Frontend Conventions
- Use Vite + Vue + TypeScript + Vuetify.
- Keep reusable UI in `apps/admin-web/src/components` and route views in `apps/admin-web/src/views`.
- Use `src/api/` for API client code.
- Prefer Vuetify components wherever possible before reaching for custom primitives.
- Use `@vuetify/v0` for shared theme/storage helpers and keep the Vuetify MCP setup in sync with project docs.
- Preserve the route-first workflow: `Overview`, `Contract`, `Flow`, `Test`, and `Deploy` are the current product mental model.

## 🧠 Documentation Rules
- When code changes behavior, update `docs/` to reflect it.
- If you add a new feature, add a short entry to `TASKS.md` and `MEMORY.md` as needed.
- If you change roadmap-level direction or architecture boundaries, update `docs/roadmap.md` and `DECISIONS.md` in the same pass.

## ✅ Task/Memo/Decision Protocol
- **TASKS.md**: update when you start/finish meaningful work.
- **MEMORY.md**: record assumptions, known risks, and current status.
- **DECISIONS.md**: add a dated entry for any architecture or platform decision.

## ✅ Definition of Done for a Task
- Code compiles and tests pass.
- Relevant docs updated.
- TASKS.md reflects completion.
- No regressions in Docker compose startup.

---

*If you're an automated agent: You are expected to keep this file up to date as you learn more about the project.*
