# Makefile for Artificer

.DEFAULT_GOAL := help

define docker_optional_env
$(if $(strip $($(1))),-e $(1)="$($(1))")
endef

UI_TEST_ADMIN_DOCKER_ENV = \
	$(call docker_optional_env,UI_TEST_ADMIN_USERNAME) \
	$(call docker_optional_env,UI_TEST_ADMIN_PASSWORD_FILE) \
	$(call docker_optional_env,UI_TEST_ADMIN_FULL_NAME) \
	$(call docker_optional_env,UI_TEST_ADMIN_EMAIL) \
	$(call docker_optional_env,UI_TEST_ADMIN_AVATAR_URL) \
	$(call docker_optional_env,UI_TEST_ADMIN_ROLE)

VERSION_SCRIPT = python3 scripts/versioning.py

help:
	@echo "Available targets:"
	@echo "  make up         # Start services (docker compose up)"
	@echo "  make down       # Stop services (docker compose down)"
	@echo "  make build      # Build docker images"
	@echo "  make logs       # Tail logs for all services"
	@echo "  make up-prod-local     # Start the local runtime stack (production-like)"
	@echo "  make down-prod-local   # Stop the local runtime stack and keep volumes"
	@echo "  make clean-prod-local  # Stop the local runtime stack and remove volumes"
	@echo "  make build-prod-local  # Build the local runtime images"
	@echo "  make logs-prod-local   # Tail logs for the local runtime stack"
	@echo "  make test       # Run backend tests"
	@echo "  make lint       # Run linting (backend + frontend)"
	@echo "  make seed       # Seed the database (run migrations + seed)"
	@echo "  make ui-test-user  # Create or reset a dedicated local admin QA account"
	@echo "  make version    # Print the canonical app version from VERSION"
	@echo "  make version-check  # Fail if version consumers drift from VERSION"
	@echo "  make version-sync   # Rewrite version consumers from VERSION"
	@echo "  make set-version VERSION=X.Y.Z[-label.N]  # Set VERSION and sync all consumers"
	@echo "  make bump-version PART=patch|minor|major|prerelease|release [PRE_LABEL=alpha]  # Compute and apply the next version"
	@echo "  make clean      # Cleanup generated artifacts"

up:
	docker compose up --build

down:
	docker compose down --volumes

build:
	docker compose build

logs:
	docker compose logs -f

up-prod-local:
	docker compose -f docker-compose.prod-local.yml up --build

down-prod-local:
	docker compose -f docker-compose.prod-local.yml down

clean-prod-local:
	docker compose -f docker-compose.prod-local.yml down --volumes

build-prod-local:
	docker compose -f docker-compose.prod-local.yml build

logs-prod-local:
	docker compose -f docker-compose.prod-local.yml logs -f

seed:
	docker compose run --rm api sh ./scripts/seed.sh

ui-test-user:
	docker compose run --rm $(UI_TEST_ADMIN_DOCKER_ENV) api python -m scripts.create_test_admin

version:
	@$(VERSION_SCRIPT) show

version-check:
	@$(VERSION_SCRIPT) check

version-sync:
	@$(VERSION_SCRIPT) sync

set-version:
	@test -n "$(VERSION)" || (echo "VERSION is required, for example: make set-version VERSION=2.0.0-alpha.2" >&2; exit 1)
	@$(VERSION_SCRIPT) set "$(VERSION)"

bump-version:
	@test -n "$(PART)" || (echo "PART is required, for example: make bump-version PART=prerelease PRE_LABEL=alpha" >&2; exit 1)
	@$(VERSION_SCRIPT) bump "$(PART)" $(if $(strip $(PRE_LABEL)),--pre-label "$(PRE_LABEL)",)

test:
	docker compose run --rm api pytest

lint:
	docker compose run --rm api black --check . && \
	docker compose run --rm admin-web npm run lint

clean:
	rm -rf .pytest_cache __pycache__ build dist
