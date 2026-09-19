# Node/VM Environment Patch

Use this profile only after a JavaScript entry and fixed browser sample already exist.

## Entry Requirements

Before patching environment values, confirm:

1. Target script or module ID.
2. Entry function, setup call, or trigger order.
3. Real input and expected output shape.
4. Browser baseline and session source.

If any item is missing, return to browser observation.

## Sandbox Rule

`node:vm` is not a security boundary. Unknown or third-party target code must run in a disposable OS/container sandbox with no credentials, no project secrets, limited filesystem access, and network disabled unless a specific replay step requires it.

## Patch Loop

1. Run the target in an empty or minimal environment and save missing paths, errors, and output.
2. Add the smallest environment module that explains the first divergence.
3. Rerun and compare missing paths, error movement, and output shape.
4. Add custom patches only for observed reads that affect output.
5. Stop when two iterations do not move the divergence, or when the missing host feature cannot be honestly simulated.

## Common Modules

Patch only what is read:

1. `navigator`: user agent, language, platform, hardware hints.
2. `location`: origin, host, path, search.
3. `document`: cookie getter/setter, basic element stubs.
4. `crypto`: random and digest boundaries when input contracts prove use.
5. `performance`: monotonic timing if elapsed time changes output.

Do not copy full browser fingerprints, storage dumps, cookies, or canvas/WebGL values into a public patch unless the task owner authorizes and the values are redacted or synthetic.

## Completion

A successful patch produces fixed-vector parity and an honest list of residual host differences. Helper load success is not enough.
