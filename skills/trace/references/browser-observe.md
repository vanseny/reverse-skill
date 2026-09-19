# Browser Observe

Use browser tools to gather evidence, not as the final solution.

## Clean Baseline

Start with a clean network buffer. Perform one user action that triggers the target request. Save the request, response, initiator, scripts, cookies, storage, and console errors before adding hooks or breakpoints.

## Sequential Tool Rule

Only one browser tool family should own the live target at a time. If switching tools, save the current baseline and record whether state is replayable. Do not run multiple target-active browsers in parallel against the same one-time session chain.

## What To Look For

1. The request that returns useful data.
2. Scripts loaded immediately before the request.
3. Fetch/XHR wrappers or client interceptors.
4. Cookie and storage writers.
5. Runtime environment reads that may affect branching.
6. Response-side refresh or decode steps.
7. WebSocket frames or async job pivots when the data is not in HTTP response bodies.

## Exit Criteria

Stop observing when you can state:

1. Which request matters.
2. Which fields move.
3. Which script or runtime boundary changes them.
4. Which evidence is still missing.

Then move to Hook, AST, env patch, or offline rebuild as needed.
