# Anti-Patterns

Use this file when a shortcut feels faster than the next proof.

## 1. Browser-backed replay as final delivery

Temptation: drive the page, call page `fetch`, or keep a browser profile as a hidden dependency.

Correct move: identify the decisive artifact the browser provides, harvest it at the nearest stable boundary, then replay with local HTTP.

Self-check: if the browser process disappears, does the collector still work?

## 2. Hardcoding rotating state

Temptation: paste the current cookie, token, nonce, or header into config because it works once.

Correct move: prove the writer, scope, expiry, refresh route, and first wire consumer. Rebuild or refresh only the authoritative artifact.

Self-check: can a fresh run recover the value without manual recapture?

## 3. Scaling after one lucky success

Temptation: add pagination, concurrency, export automation, or runtime shrinking after one good page.

Correct move: replay the smallest request twice, then prove one next cursor or page with the same chain.

Self-check: does the same single-page request still pass on a fresh repeat?

## 4. Jumping multiple runtime rungs

Temptation: Python mismatch -> broad runtime; runtime loads -> broad host patch; one blocked route -> transport cargo cult.

Correct move: record the last working proof, the exact blind spot, why the next rung is smallest, and why browser-free delivery survives.

Self-check: can you name the exact failure the heavier layer answers?

## 5. Broad hooks before a clean baseline

Temptation: install global hooks or breakpoints before freezing one untouched request.

Correct move: capture a clean request/response pair first, then move hooks toward the narrowest stable boundary.

Self-check: did behavior change only after instrumentation landed?

## 6. Reversing the visible placeholder

Temptation: chase a visible `sign` variable or business payload before checking final egress.

Correct move: trace the canonical mutation point and rebuild exactly what crosses the wire.

Self-check: does the local artifact match the final request slot, framing, and serialization?

## 7. Treating helper health as protocol success

Temptation: fewer exceptions, non-empty output, plausible token length, or browser-shaped cookies feel done.

Correct move: compare fixed vectors, then replay the real request and check business semantics.

Self-check: did a server-validated request accept the artifact on a fresh chain?

## 8. Mixing sibling route assumptions

Temptation: reuse field order, signer coverage, or cursor rules from a nearby endpoint.

Correct move: compare method, query, body, content type, headers, and signer coverage before sharing helpers.

Self-check: does the same helper pass on both routes with route-specific fixed vectors?

## 9. Ignoring response decode order

Temptation: decode until text appears, then bake that sequence into the collector.

Correct move: preserve prefix strip, compression, Base64, binary envelope, protobuf/JSON order, and every failure mode.

Self-check: can one frozen payload fail when one decode step is removed or reordered?

## 10. Storing stories instead of verifiable facts

Temptation: write long notes like "the site is strict" or "the runtime is needed".

Correct move: store 5 to 15 measurable facts: endpoint, field slot, artifact shape, decode order, session binding, replay count.

Self-check: can a later run re-check each line as true, changed, or unknown?
