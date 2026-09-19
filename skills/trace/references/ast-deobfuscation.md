# AST Deobfuscation

Use this profile when the user needs targeted source restoration, not when the request contract is still unknown.

## Boundary

Use AST work for:

1. String-array and decoder-call recovery.
2. Object dispatcher simplification.
3. Control-flow simplification.
4. Dead-code and self-defense cleanup.
5. Readable intermediate outputs.

Return to browser observation when the function location, script URL, or request boundary is still unknown.

## Standard Output Layout

```text
source/original/target.js
source/deobfuscated/target_deobf.js
intermediate/target_step1.js
intermediate/target_step2.js
analysis/ast_report.md
```

## Process

1. Save the original file first.
2. Parse and check encoding, BOM, invisible characters, and syntax errors.
3. Run one reversible pass at a time.
4. Generate code after each pass.
5. Reparse generated output before continuing.
6. Keep intermediate files.
7. Stop before aggressive inlining when runtime state is required.

## Validation

Do not claim the restored code is correct only because it is readable. Validate with syntax parsing, residue counts, known fixed vectors, or a narrow runtime fixture when safe.

## Failure Modes

| Trigger | Action | Fallback |
|---|---|---|
| Parse fails | Save step0 and clean encoding | Produce character-level report |
| Family unknown | Run low-risk common passes only | Stop with residual notes |
| Pass breaks syntax | Revert to previous step | Disable that pass |
| Runtime state required | Stop at readable or instrumented output | Return to observation or env patch |
