# Codex Local Setup

This folder contains project-scoped Codex configuration for `urban-octo-bassoon`.

It is intentionally local-only and excluded from git so this repo can keep a tailored agent lineup without affecting other repositories on the machine.

## Environment Variables

Set these before starting Codex in this repository:

- `CONTEXT7_API_KEY`: used by `docs_researcher` for Context7 docs lookup.
- `GITHUB_PERSONAL_ACCESS_TOKEN`: used by `feature_developer`, `ui_feature_developer`, `bugfix_developer`, and `release_manager` for GitHub-aware work such as PRs and issue context.

Example shell setup:

```bash
export CONTEXT7_API_KEY="your-context7-key"
export GITHUB_PERSONAL_ACCESS_TOKEN="your-github-token"
```

## Agent Lineup

- `task_orchestrator`: default task lead for `TASKS.md`-driven work; decides which specialist agents are actually needed.
- `feature_developer`: main implementation agent for new features, branch work, pushes, and PR-aware development.
- `ui_feature_developer`: frontend implementation agent for new Vue/Vuetify features and user-facing workflow changes.
- `bugfix_developer`: narrow reproduce-fix-verify agent for regressions and behavior fixes.
- `release_manager`: branch, commit, push, PR, and release coordination.
- `browser_debugger`: browser repro, console, network, and interaction evidence.
- `ui_tester`: task-based browser tester that tries to complete the UI like a normal user.
- `ui_reviewer`: UX and workflow review for the admin/public route experience.
- `a11y_reviewer`: accessibility review for keyboard flow, semantics, focus, and labels.
- `security_reviewer`: auth, permissions, injection, secrets, and runtime-boundary review.
- `db_migration_reviewer`: Alembic, SQLModel, Postgres, and migration-safety review.
- `docs_researcher`: official docs lookup for OpenAI, FastAPI, Vue/Vuetify, and libraries.
- `documentation_agent`: project-docs maintainer for concise, accurate updates across repo documentation and tracking files.

## Prompt Patterns

These prompt patterns are documented here in this file: [README.md](/home/devadmin/projects/urban-octo-bassoon/.codex/README.md), under `Prompt Patterns` and `Recommended Workflows`.

Use the main agent by default and only call out a specialist when the task clearly benefits from it.

### Default Orchestrated Task

```text
Use task_orchestrator.
Work on the next meaningful item in TASKS.md.
Read the required project context first, use `docs_researcher` before implementation when framework or API behavior is uncertain, choose the minimum useful specialist agents, implement the work, run the relevant verification, and update branch/PR state only if needed.
```

### Default Orchestrated Task With Git Flow

```text
Use task_orchestrator.
Work on the next meaningful item in TASKS.md.
Create a branch, use `docs_researcher` before implementation when framework or API behavior is uncertain, choose the minimum useful specialist agents, implement the work in reviewable commits, run the relevant tests, push the branch, and open or update the PR if appropriate.
```

### Orchestrated Task With Explicit Review Gates

```text
Use task_orchestrator.
Work on the next task in TASKS.md that is ready to execute.
Use the fewest specialist agents needed, but include security_reviewer for auth/runtime/public-surface changes, db_migration_reviewer for schema changes, ui_tester for task-based user-visible workflow validation, and ui_reviewer for workflow/UX review when the interface changes materially.
Implement the work, verify it, and summarize what changed plus any remaining risks.
```

### Feature Work

```text
Use feature_developer for this task.
Create a new branch, implement the feature in small reviewable commits, run the relevant tests, push the branch, and open or update the PR if needed.
Task: ...
```

### UI Feature Work

```text
Use ui_feature_developer for this task.
If framework or library behavior is uncertain, use docs_researcher first.
First verify whether the existing stack is already serving `http://localhost:3000` and `http://localhost:8000/api/health`; only start missing services, and prefer `docker compose up --build -d` over `make up`.
For browser validation, sign in through the normal login UI with a dedicated QA account created via `make ui-test-user`, not the shared bootstrap admin.
Implement the user-facing change in small reviewable commits, run the relevant frontend tests, and use ui_tester when the workflow needs realistic end-user validation.
Task: ...
```

### Bug Fix

```text
Use bugfix_developer for this task.
Reproduce the issue first, implement the smallest safe fix, add regression coverage if practical, run the relevant tests, and push the branch.
Task: ...
```

### PR / Release Mechanics

```text
Use release_manager.
Create or update the branch, clean up commits if needed, push the branch, open or update the PR, and summarize what shipped.
Context: ...
```

### UI Investigation

```text
Use browser_debugger first, then ui_reviewer if needed.
Reproduce the issue in the browser, capture exact repro steps plus console/network evidence, then review the UX impact.
Issue: ...
```

### Accessibility Review

```text
Use a11y_reviewer.
Review this flow for keyboard access, focus order, labeling, semantics, and screen-reader-visible regressions.
Scope: ...
```

### Security Review

```text
Use security_reviewer.
Review this change for auth, authorization, injection, secret handling, connector/runtime trust boundaries, and realistic exploit paths.
Scope: ...
```

### Migration Review

```text
Use db_migration_reviewer.
Review this Alembic or schema change for Postgres safety, backfill risk, lock-heavy DDL, downgrade realism, and model drift.
Scope: ...
```

### Docs Lookup

```text
Use docs_researcher.
Verify the official docs for this API/framework behavior and cite the authoritative source before we implement anything.
Question: ...
```

### Documentation Maintenance

```text
Use documentation_agent.
Read the relevant code and docs first, then update the project documentation so it is accurate, readable, concise, and consistent across docs/, TASKS.md, MEMORY.md, and DECISIONS.md where needed.
Scope: ...
```

### UI Testing

```text
Use ui_tester.
First verify whether the existing stack is already serving `http://localhost:3000` and `http://localhost:8000/api/health`; only start missing services, and prefer `docker compose up --build -d` over `make up`.
If auth is required and no current credential is provided, create or reset a dedicated QA account with `make ui-test-user`, sign in through the normal login UI, then attempt the workflow like a normal user and report concrete blockers, confusing states, and supporting repro evidence.
Task: ...
```

### Generic “Just Move the Repo Forward” Prompt

```text
Use task_orchestrator.
Pick up the next high-value task from TASKS.md, make reasonable decisions, use only the specialist agents that are clearly useful, and carry the work through implementation and verification.
If branch or PR work becomes relevant, bring in release_manager.
```

## Recommended Workflows

### Standard Feature Cycle

1. Ask for `ui_feature_developer` for net-new frontend workflow work, or `feature_developer` for backend/full-stack feature work.
2. Use `docs_researcher` first when framework, library, or API behavior is uncertain.
3. For user-visible workflow changes, use dedicated QA accounts through `make ui-test-user` instead of the shared bootstrap admin; then use `ui_tester` to attempt the task like a normal user, and `ui_reviewer` if you want product/UX critique.
4. If the change touches auth, connectors, runtime trust boundaries, or public surfaces, ask for `security_reviewer`.
5. If the change includes Alembic or SQLModel schema changes, ask for `db_migration_reviewer`.
6. Use `documentation_agent` when the repo docs need a cleanup or consistency pass after the code lands.
7. Ask for `release_manager` if you want help with PR creation, PR updates, or release notes.

### Standard Bugfix Cycle

1. Ask for `bugfix_developer`.
2. Use `ui_tester` first when the question is whether a normal user can complete the workflow; use `browser_debugger` first when the issue is timing-sensitive, browser-specific, or needs console/network evidence.
3. Add `ui_reviewer`, `security_reviewer`, or `db_migration_reviewer` only when the fix touches those concerns.
4. Use `release_manager` for branch/PR cleanup and shipping.

### Standard “Work On The Next Task” Cycle

1. Ask for `task_orchestrator`.
2. Let it choose `ui_feature_developer`, `feature_developer`, or `bugfix_developer` based on whether the next item is UI feature work, backend/full-stack net-new work, or a regression fix.
3. Add `ui_tester`, `browser_debugger`, `ui_reviewer`, `a11y_reviewer`, `security_reviewer`, `db_migration_reviewer`, `docs_researcher`, or `documentation_agent` only when the task genuinely needs that expertise.
4. Use `release_manager` only when you want branch, push, PR, or release coordination.

## Notes

- Keep GitHub-aware roles narrow so GitHub MCP is only started when it is actually needed.
- Keep docs lookups on `docs_researcher` so the main agent stays lean.
- Use `documentation_agent` for repo-doc upkeep and `ui_tester` for realistic end-user workflow checks; they solve different problems than `docs_researcher` and `ui_reviewer`.
- For authenticated browser work, prefer dedicated QA accounts created with `make ui-test-user`; do not normalize reuse of the shared bootstrap admin for UI agents.
- For local browser work, verify and reuse the existing Compose stack before starting anything; do not churn containers or port bindings just to begin a test session.
- Prefer one strong implementation agent plus one targeted reviewer over spawning many agents at once.
- `task_orchestrator` should be the default entrypoint when you want Codex to decide which specialists to involve.
