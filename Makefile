# Makefile for Mockingbird

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

test:
	docker compose run --rm api pytest

lint:
	docker compose run --rm api black --check . && \
	docker compose run --rm admin-web npm run lint

clean:
	rm -rf .pytest_cache __pycache__ build dist
