# Response Templating Scope

This document scopes the first pass of response templating so Artificer can support richer dynamic payloads without abandoning the drag-and-drop schema studio.

Current status: the phase 1 backend/runtime support, schema-studio inspector controls, helper chips, and request-aware preview inputs are now implemented on top of this scope, with the preview-context form living below the canvas so the live-preview pane can stay focused on output.

## Goals
- Keep `response_schema` as the single source of truth for response shape, preview output, runtime output, and OpenAPI publishing.
- Preserve the builder-first authoring flow: drag/drop structure in the canvas, edit details in the inspector, and treat templating as a node-level enhancement instead of a second authoring mode.
- Reuse one internal contract across the admin preview API and the public runtime dispatcher.
- Keep deterministic output compatible with the existing `seed_key` behavior.
- Continue stripping internal authoring metadata from public OpenAPI and public reference output.

## Non-goals
- A raw full-response Handlebars/Liquid editor that bypasses the schema studio.
- Arbitrary code execution or unrestricted helper functions inside templates.
- Request-schema templating.
- Tuple-array or block/loop authoring in v1.
- Cross-field response references in v1; those introduce ordering and cycle concerns that are better handled after the first pass ships.

## Proposed Phase 1 Contract

Phase 1 adds an optional `x-mock.template` string to response-side `string` nodes.

```json
{
  "type": "string",
  "format": "uri",
  "x-mock": {
    "mode": "generate",
    "type": "url",
    "options": {},
    "template": "https://artificer.test/orders/{{request.path.orderId}}?source={{value}}"
  }
}
```

Rules:
- `x-mock.template` is only valid on response `string` nodes in phase 1.
- Existing `x-mock.mode`, `x-mock.type`, `x-mock.generator`, `x-mock.options`, and path-parameter linking stay unchanged.
- The node still produces a base value first using the current mode/value-type behavior.
- The template then renders a final string by interpolating request-aware tokens into that base value.
- If `x-mock.template` is absent or blank, the node behaves exactly as it does today.
- `x-mock.template` is internal metadata and must be stripped anywhere public schemas already strip `x-mock`.

This keeps the schema studio in charge of shape, type, ordering, and constraints while giving string fields a controlled escape hatch for richer composition.

## Template Context

Phase 1 should support only a small, explicit context:

- `{{value}}`
  The base value generated for the current node from its existing `x-mock` mode/type behavior.
- `{{request.path.<name>}}`
  The matched route placeholder value, for example `{{request.path.orderId}}`.
- `{{request.query.<name>}}`
  A query parameter supplied at preview/runtime, for example `{{request.query.status}}`.
- `{{request.body.<path>}}`
  A JSON-path-like lookup into the request body, for example `{{request.body.customer.email}}`.

Phase 1 intentionally does not include:
- `{{response.*}}` sibling/ancestor references
- loops or conditionals
- custom helpers beyond the fixed roots above

That narrower context keeps rendering deterministic, avoids dependency graphs between response fields, and keeps the preview/runtime plumbing understandable.

## Rendering Order

Phase 1 should render templated nodes in two passes:

1. Normalize `response_schema` exactly as today, preserving `x-mock.template` on valid string nodes.
2. Generate the base response tree using the current `generate` / `mocking` / `fixed` / linked-path logic.
3. Walk the same tree again and render `x-mock.template` strings against the request context plus each node's base `value`.
4. Apply existing JSON serialization and response delivery behavior.

Important consequences:
- Templates can wrap or reshape a node's own generated value through `{{value}}`.
- Templates do not change the response tree shape; they only replace the final string content of an existing string field.
- `x-builder.order` and the array `Item shape` model remain untouched because templating happens inside nodes, not around the tree.

## Validation Rules

Phase 1 validation should stay conservative:

- Reject `x-mock.template` on non-string response nodes.
- Reject malformed placeholders or unsupported roots.
- Validate `request.path.<name>` against the saved route placeholder list when available.
- Treat missing `request.query.*` and `request.body.*` values as empty strings at runtime/preview instead of failing the whole response.
- Keep existing string constraints in force after rendering; if a template produces a string longer than `maxLength`, preview/runtime should still apply the saved schema constraints consistently.

## Admin UI Shape

The schema studio remains the primary authoring surface.

Phase 1 UI should add template controls only in the response-string inspector:
- A toggle such as `Use template`
- A multiline `Template` field
- Small helper chips for inserting `{{value}}`, current path params, current query params, and common request-body prefixes
- Preview feedback in the existing live-preview surface, while keeping the request-context form outside the narrow preview pane

Phase 1 should not add:
- a second raw-response editor tab
- drag targets or canvas pills dedicated to template syntax
- templating controls on request nodes

That keeps the current pill-tree WYSIWYG flow intact and makes templating feel like an advanced field option rather than a competing editor.

## Backend and Preview Plumbing

Phase 1 implementation needs one request-aware context shape shared by admin preview and public runtime:

- Public runtime should pass path params, query params, and parsed JSON body into response generation.
- `POST /api/admin/endpoints/preview-response` should grow matching optional inputs for query params and request body so studio previews can render the same template tokens the public route will see.
- The response generator should own template rendering so both preview and public runtime stay aligned.

## OpenAPI and Public Output

Templating stays internal:
- OpenAPI generation should continue publishing only sanitized JSON Schema, with `x-mock.template` removed alongside the rest of `x-mock`.
- Public reference responses should continue using generated sample payloads, but the internal template metadata itself must never be exposed.

## Implementation Slices

Recommended order:

1. Backend contract and rendering
   Add `x-mock.template` normalization/validation, extend preview/runtime request context, render templates in the generator, and cover it with backend tests.
2. Schema studio controls
   Add response-string inspector controls, helper-token insertion, and frontend validation/tests.
3. Preview and docs polish
   Show template-aware preview examples clearly, document the feature, and verify OpenAPI/public schema sanitization still holds.

## Future Expansion

If phase 1 lands cleanly, later iterations can consider:
- response-field references such as `{{response.customer.id}}` once dependency ordering is explicit
- array item context such as `{{item.index}}`
- curated helpers such as casing or slug transforms
- an opt-in engine/version field if we ever need a larger Handlebars/Liquid-compatible surface
- structured object/array escape hatches that still preserve the builder-owned outer shape

The guardrail for all future work stays the same: richer authoring is welcome, but the schema studio must remain the primary way users shape responses.
