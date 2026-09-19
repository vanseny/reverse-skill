# Report Template

Reports should be short, comparable, and redacted.

## Redaction Rule

Report secret names, provenance, scope, expiry, and short hashes. Do not paste raw cookies, tokens, passwords, authorization headers, proxy credentials, private keys, or account identifiers into chat, fixtures, or shared reports.

## Phase Delta

```markdown
Phase Delta
- New evidence:
- Changed hypothesis:
- Intake/capability change:
- Evidence path and SHA-256:
- First divergence:
- Next smallest proof:
```

## Recon

```markdown
Recon
- Target:
- Mode: live-target / artifact-only / continuation
- Real request candidates:
- Useful data source: HTML / XHR / Fetch / GraphQL / WebSocket / binary / other
- Key headers: names and provenance only
- Key cookies: names, writer, scope, expiry, hash
- Decode needed:
- Misleading signals:
- Next hypothesis:
```

## Implementation Decision

```markdown
Implementation Decision
- Delivery shape: Python / Python + JS / Python + WASM / Python + iv8 / blocked
- Why this shape:
- Required session state:
- Required headers:
- Required cookies:
- Required helper outputs:
- Required decode chain:
- Known risks:
```

## Final Delivery

```markdown
Final Delivery
- Collector path:
- Intake mode:
- Real endpoint:
- Moving parts:
- Helper boundary:
- Fixed vectors:
- Replay count:
- Pagination confirmed:
- Browser dependency: none / blocked reason
- Residual risks:
```

## Minimal Verifiable Facts

After a reusable win, preserve 5 to 15 facts:

```markdown
Minimal Verifiable Facts
- Family or route:
- Fact 1:
- Fact 2:
- Fact 3:
- Fact 4:
- Fact 5:
```

Each fact must be observable, measurable, and safe to store without raw secrets.
