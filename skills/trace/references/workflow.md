# Workflow

Use this as the shortest end-to-end map for a Trace task.

## Startup

Classify the task before using deep tools:

1. `live-target`: a current page or endpoint needs fresh wire/runtime evidence.
2. `artifact-only`: saved captures, scripts, tokens, cookies, or responses are enough for the next proof.
3. `continuation`: target, session assumptions, tool registry, and delivery goal remain current.

For `live-target`, record available browser/debug/runtime tools, selected fallback, and blockers. Do not open the same target in multiple browser families just to prove availability.

## Phase 1: Real Request

Capture the request that returns useful data. Save exact URL, method, query, body, headers, outbound cookies, response shape, redirect chain, and initiator. Treat wire egress as authoritative when it differs from intermediate values.

## Phase 2: Moving State

List every field that changes between successful attempts. Assign each field to a source class: time, nonce, cookie writer, request signer, response refresh, decode key, pagination cursor, transport property, or session state.

## Phase 3: Mutation Point

Find where the wire-shaped payload changes. Common places are fetch/XHR wrappers, request interceptors, serializers, bootstrap scripts, exposed helpers, WASM exports, and response-side refresh handlers.

## Phase 4: Offline Rebuild

Start with fixed-input parity. Only widen runtime when the current rung is proven insufficient. Prefer pure Python, then a small JS/WASM helper, then basic iv8 for a known entry with fixed samples.

## Phase 5: Replay

Run one coherent session chain. Confirm business semantics, not just HTTP status. Repeat a fresh single-page replay before pagination, concurrency, or packaging.

## Handoff

When switching stages, save a `handoff.json` with:

```json
{
  "task_id": "stable-id",
  "mode": "live-target",
  "current_stage": "Observe",
  "target_url": "https://example.test/api",
  "target_method": "POST",
  "target_fields": ["x-sign"],
  "baseline_id": "source-session-time",
  "artifacts": {},
  "success_predicate": "fixed input and live replay match",
  "unresolved": []
}
```

Keep handoff files redacted and task-local.
