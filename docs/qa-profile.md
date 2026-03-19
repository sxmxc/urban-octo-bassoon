# QA Profile

This repo now has two practical local Docker modes:

## Local development
- `make up`
- Uses [docker-compose.yml](/home/devadmin/projects/artificer/docker-compose.yml)
- Builds the Dockerfiles' `dev` targets
- API runs with `uvicorn --reload`
- Admin runs through the Vite dev server

## Local production-like QA
- `make up-prod-local`
- Uses [docker-compose.prod-local.yml](/home/devadmin/projects/artificer/docker-compose.prod-local.yml)
- Builds the Dockerfiles' `runtime` targets from the local checkout
- API runs through `start.prod.sh`
- Admin serves the built SPA through Nginx and proxies `/api` to the backend container

Both modes keep the same service names, default Compose project, and named Postgres volume, so switching modes recreates the same local stack in place instead of spinning up a second database. Use `make down-prod-local` to stop the production-like stack without deleting volumes, or `make clean-prod-local` if you want a fresh DB too.
