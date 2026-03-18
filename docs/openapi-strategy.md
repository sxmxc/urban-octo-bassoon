# OpenAPI Strategy

The OpenAPI spec must always reflect the active public API contract stored in the database.

## Approach
- **Source of truth**: `EndpointDefinition` records in Postgres.
- **Generation**: Build the OpenAPI object dynamically on each request to `/openapi.json`.
- **Caching**: For v1, keep it simple and rebuild on demand; add caching later if performance becomes a concern.
- **Public alignment**: The branded landing page and `/api/reference.json` should read from the same active catalog so human-facing and machine-facing references do not drift.

## Transition state

Today:
- OpenAPI is still generated from enabled `EndpointDefinition` rows.
- The live runtime can already dispatch through published `RouteDeployment` records first.

Target state:
- OpenAPI should reflect the published public contract boundary, not merely any enabled draft route.
- Public contract publishing should stay based on `request_schema` and `response_schema`, not on raw flow-node internals.

## Key mechanics
- Each active endpoint becomes an OpenAPI path entry.
- The `method`, `path`, `summary`, `description`, and schemas drive the OpenAPI operation fields.
- Internal builder and generator extensions (`x-builder`, `x-mock`, including semantic mock value types and response-template metadata) are removed before publishing the public schema.
- Any validation errors in schemas should be surfaced when saving an endpoint.

## Guardrails

- Do not generate OpenAPI from `flow_definition`.
- Do not leak connector metadata, secrets, or execution-node configuration into the public spec.
- When the publish boundary is tightened, update `/openapi.json`, `/api/reference.json`, and the public landing page together so those surfaces keep moving in lockstep.

## Developer notes
- When tweaking the endpoint schema model, update both the generation logic and the docs.
- Keep the generation logic in one place to avoid drift.
- The next major OpenAPI task is to align public contract publishing with the new deployment model without breaking the current route authoring workflow.
