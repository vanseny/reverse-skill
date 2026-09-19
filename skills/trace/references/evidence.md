# Evidence

Evidence should be fresh, ordered, and redacted.

## Minimum Capture

For a business request, collect:

1. Request URL, method, query, body bytes, and content type.
2. Request headers after browser/network wrappers finish.
3. Outbound Cookie header exactly as sent.
4. Response status, headers, body shape, and redirect chain.
5. Initiator stack or closest script/function boundary.
6. Related storage, cookie writes, and bootstrap assets.

## Cookie Provenance

Never treat every cookie surface as the same thing. Track:

1. `Set-Cookie` response source.
2. `document.cookie` writer source.
3. Browser jar value.
4. Outbound Cookie header consumer.
5. Scope, path, expiry, refresh route, and first downstream consumer.

## Fixed Vectors

Before porting code, freeze at least one vector:

```json
{
  "input": {"query": {}, "body": {}, "headers": {}},
  "expected": {"field": "known-output-shape"},
  "source": "browser-capture-id",
  "captured_at": "ISO-8601 timestamp"
}
```

Use fixed vectors for first-divergence debugging. Do not use expired samples as live acceptance.

## Redaction

Remove or hash cookies, authorization headers, raw account IDs, private tokens, proxy credentials, browser profiles, and complete request bodies when they contain personal data. Keep shape and field names when they are needed for debugging.
