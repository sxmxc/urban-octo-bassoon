# Contributing to Artificer

Thanks for contributing! This project is designed to be friendly to both humans and AI agents. Please follow the lightweight conventions below.

## 🧭 Before you start
1. Read `AGENTS.md`, `TASKS.md`, `MEMORY.md`, and `DECISIONS.md`.
2. Look for an existing task in `TASKS.md` that matches what you want to work on.
3. If there is no task, add one under the appropriate section (Now/Next/Later).

## 📦 Workflow
- Use `make up` to start the development environment.
- Run `make test` before opening a PR.
- Keep changes focused and reviewable; smaller PRs are better.

## 📝 Coding standards
- Follow Python formatting conventions (Black).
- Keep TypeScript types clear and avoid `any` unless necessary.

## ✅ Documentation
- When you add or change behavior, update relevant docs in `docs/`.
- If you add a new feature, add a note to `TASKS.md` and `MEMORY.md`.

## 🧠 Decision logging
- If you make an architectural decision, add a dated entry in `DECISIONS.md`.

## 🧩 PR Checklist
- [ ] Code builds and tests pass.
- [ ] Documentation is updated (if applicable).
- [ ] TASKS.md and/or MEMORY.md updated (if applicable).
- [ ] No unresolved TODOs in code.
