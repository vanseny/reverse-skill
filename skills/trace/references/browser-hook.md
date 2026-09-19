# Browser Hook

Use this profile for narrow observation at a known boundary. Hooks are temporary evidence tools. Remove them after capture and re-check clean behavior.

## Rules

1. Hook the smallest object or function that can answer the question.
2. Log arguments, return values, selected headers, URL, and stack only when needed.
3. Do not mutate production behavior unless the task explicitly requires an interceptor proof.
4. Reproduce once without hooks before using the result as acceptance.

## Fetch Observer

```js
(() => {
  const originalFetch = window.fetch;
  window.fetch = async function (...args) {
    const stack = new Error().stack;
    console.log("[trace:fetch]", args[0], args[1], stack);
    const response = await originalFetch.apply(this, args);
    console.log("[trace:fetch:response]", response.url, response.status);
    return response;
  };
})();
```

## XHR Observer

```js
(() => {
  const open = XMLHttpRequest.prototype.open;
  const send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this.__trace = { method, url, stack: new Error().stack };
    return open.call(this, method, url, ...rest);
  };
  XMLHttpRequest.prototype.send = function (body) {
    console.log("[trace:xhr]", this.__trace, body);
    return send.call(this, body);
  };
})();
```

## Cookie Write Observer

```js
(() => {
  const desc = Object.getOwnPropertyDescriptor(Document.prototype, "cookie") ||
    Object.getOwnPropertyDescriptor(HTMLDocument.prototype, "cookie");
  if (!desc || !desc.set || !desc.get) return;
  Object.defineProperty(document, "cookie", {
    configurable: true,
    get() { return desc.get.call(document); },
    set(value) {
      console.log("[trace:cookie:set]", value, new Error().stack);
      return desc.set.call(document, value);
    }
  });
})();
```

## Output

Report the exact hook, what it observed, which stack or script it identified, and whether clean replay without the hook still behaves the same.
