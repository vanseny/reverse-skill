# Basic iv8 Usage

This public release only covers basic iv8 routing and usage rules. It does not include private protocol profiles or site-specific cases.

## When To Use

Use iv8 only when:

1. The user explicitly chooses Python plus iv8.
2. A known JavaScript entry or lifecycle trigger exists.
3. Fresh HTML, script, seed data, cookies, and expected output are available from the same session chain.
4. Pure Python or a small JS helper is riskier than running the target code locally.

If the entry is unknown, return to browser observation. If fixed samples are missing, capture them before implementing.

## Minimal Flow

1. Use one Python session for the entry page, script fetches, helper execution, and replay request.
2. Save volatile HTML, scripts, and runtime material under `js_reverse_cache/`.
3. Configure only the environment fields actually read by the target code.
4. Trigger the known entry or page lifecycle.
5. Extract the generated URL, headers, cookie update, body, or token.
6. Merge the output back into the same Python session and replay the request.

## Verification

Check:

1. Fixed output shape and key fields.
2. Fresh generation at least twice.
3. Server response semantics, not only HTTP status.
4. Cookie and session continuity.
5. Clear failure notes when iv8 cannot represent a browser feature.

## Boundaries

Do not turn iv8 into a broad browser substitute. Keep the helper narrow, avoid generic frameworks, and report the exact entry, materials, output, replay result, and residual gaps.
