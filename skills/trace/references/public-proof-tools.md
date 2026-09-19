# Public Proof Tools

These small scripts make the free Trace package less abstract without shipping private case material.

## Scripts

| Script | Purpose |
|---|---|
| `scripts/protocol_diff.py` | Compare two JSON/text protocol samples and show structural differences. |
| `scripts/crypto_fingerprint.py` | Print basic length/alphabet hints for suspicious sign/token/ciphertext strings. |
| `scripts/public_proof_lab.py` | Run deterministic local checks for exact-wire bytes, modified digest parity, and decode order. |

## Suggested Use

1. Normalize and redact captures manually or with your own tooling.
2. Use `protocol_diff.py` to compare one browser capture against one local replay.
3. Use `crypto_fingerprint.py` only for hints. It does not identify algorithms with certainty.
4. Use `public_proof_lab.py --self-test` to demonstrate why exact bytes, digest masks, and decode order matter.

## Acceptance

These tools are proof aids, not success gates by themselves. A task is complete only when the startup success predicate is met: fixed-vector parity, fresh replay, server-validated response, or explicitly labeled artifact-only analysis.
