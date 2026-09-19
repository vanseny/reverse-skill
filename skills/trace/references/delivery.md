# Delivery

The final output should make the result repeatable and auditable.

## Deliverables

Provide:

1. Confirmed request contract.
2. Moving fields and their refresh source.
3. Helper boundary and reason for keeping it.
4. Fixed vectors or artifact-only limitation.
5. Fresh replay proof when authorized.
6. Redacted report with residual risk.

## Proof Manifest

Use a task-local manifest such as:

```json
{
  "mode": "live-target",
  "delivery": "pure-python-or-helper",
  "request_contract": "analysis/request-contract.json",
  "fixed_vectors": ["fixtures/vector-001.json"],
  "live_replay_count": 2,
  "browser_free": true,
  "runtime_free": false,
  "helper_boundary": "known JS entry only",
  "residual_risks": []
}
```

## Acceptance Rules

Do not mark complete when only one of these is true:

1. A helper loads.
2. Output is non-empty.
3. Token length looks plausible.
4. HTTP status is 200.
5. Browser replay still works.
6. Old cookies or samples still pass locally.

Completion requires the stated success predicate from the startup gate.
