# Baidu Passport Spin V2 Workflow

Use this reference for Baidu Passport rotate/spin captchas where the visible UI says Baidu security verification and the network chain uses `passport.baidu.com/cap/*`.

## Signals

Select this workflow when at least two independent signals appear:

1. Requests to `https://passport.baidu.com/cap/init`, `/cap/style`, `/cap/img`, and `/cap/log`.
2. `style` response contains `captchalist[0].id == "spin-0"`, `type == "spin"`, `backstr`, `ext.p`, or `ext.en_conf`.
3. JavaScript sources include `mkd_v2.js`, `work.js`, `fingerprint.js`, `getNewKey`, `powMap`, `rzData`, `secondHandle`, `dataSubmit`, or `verifyScreen`.
4. The final verifier submit is a `POST /cap/log` whose form includes `cv=submit`, `typeid=spin-0`, and a long `fs` value.

Do not use this workflow for ordinary Baidu login SMS checks, site-owner business forms, generic Baidu analytics beacons, or non-spin Passport captcha types until current evidence shows the same `spin-0` proof builder.

## Request Chain

Freeze one coherent round. Do not mix `tk`, `as`, `backstr`, image URL, `ext.p`, `en_conf`, PoW, or `fs` across adjacent rounds.

1. `POST https://passport.baidu.com/cap/init`
   - request fields: `_`, `ak`, `as`, `ds`, `refer`, `reinit`, `scene`, `tk`, `ver=2`
   - response fields: `tk`, `as`, `ds`, `ls`, `conf`
2. `POST https://passport.baidu.com/cap/style`
   - request fields: `_`, `ak`, `isios=0`, `refer`, `scene`, `tk`, `type=click`, `ver=2`
   - response fields: `backstr`, `captchalist[].source.back.path`, `ext.p`, `ext.en_conf`
3. `GET https://passport.baidu.com/cap/img?...`
   - returns the circular rotated image for the same round
4. `POST https://passport.baidu.com/cap/log`
   - telemetry and verifier submit share this URL
   - verifier submit includes `cv=submit`, `typeid=spin-0`, `fuid` optional, and encrypted `fs`

### Scene / `ak` binding

`ak` and `scene` are product-bound. Do not mix them across hosts or flows.

Observed examples (evidence only; always re-read live requests):

| Context | Example signal |
|---|---|
| 百度搜索资源平台 / linksubmit security popup | `scene=search`, host `ziyuan.baidu.com`, product `ak` on `/cap/*` |
| Passport login wall | `scene=login`, different `ak` |

Same host can emit both login-wall captcha and post-login security captcha. Capture the current popup's `/cap/init` body before hardcoding `ak`/`scene`.

## Success Marker

`/cap/log` is overloaded. `code == 0` and `msg == "Success"` are not enough.

Verifier success is:

```text
response.code == 0 && response.data.op == 1
```

Observed meanings:

| Field | Meaning |
|---|---|
| `data.op == 1` | spin verification passed |
| `data.op == 2` | single-step success / intermediate state in multi-step flows |
| `data.op == 3` | failed verification; refresh the round before the next guess |
| `data.opp == 3` | risk / packaging / session signal; stop blind angle retries and diff `fs` / `fuid` / cookies first |
| no `data.op` | usually telemetry-only `/cap/log`, not a verifier submit |

To identify the real verification packet in a browser capture, filter `cap/log` and then inspect payload/response:

1. real submit: request has `cv=submit` and `typeid=spin-0`; response has `data.op`
2. telemetry: request has only `_`, `refer`, `ak`, `as`, `scene`, `tk`, `ver`, `fs`; response has only `as`, `ds`, `tk`

## JavaScript Anchors

Primary source is `mkd_v2.js`. `work.js` owns the PoW loop. `fingerprint.js` may provide `fuid` through `window.passFingerPrint()`.

Useful searches:

1. `getNewKey` for key derivation.
2. `.fs=` or `n.fs=` for the double AES packaging.
3. `this.rzData` for the plaintext proof shape.
4. `secondHandle` and `en_conf` for the first AES layer configuration.
5. `powMap`, `originStr`, `fillZero`, `md5Pow`, `sha1Pow` for PoW.
6. `dataSubmit` for the real submit event that sets `cv=submit` and `typeid`.
7. `verifyScreen` and `setScreen` for `captchalist[id].cr` and `captchalist[id].back` geometry.

## Crypto And Proof Builder

### `getNewKey(as)`

The key material is `as + "appsapi2"`. Choose the hash by the last character of `as`, then take the first 16 hex chars.

| Last char | Hash |
|---|---|
| `A-G` / `a-g` | MD5 |
| `H-N` / `h-n` | SHA1 |
| `O-T` / `o-t` | SHA256 |
| `U-Z` / `u-z` | SHA512 |
| `0-4` | SHA3-256 |
| `5-9` | SHA3-512 |

Important: CryptoJS `SHA3` is Keccak. Python `hashlib.sha3_*` is not compatible; use `Crypto.Hash.keccak` from `pycryptodome` for parity.

### AES

`encryptMap` uses AES-ECB with CryptoJS ZeroPadding and Base64 output. The key is:

```text
params.key || getNewKey(params.as)
```

Empty-string `key` must fall back to `getNewKey(as)`. Do not pass `""` into AES as a literal key.

`ext.en_conf` decrypts with `getNewKey(as)` and usually yields a `secondHandle` like:

```json
{"method":"aes-ecb","key":"","custom":"","as":"<current-as>"}
```

After decrypt, inject/overwrite `as` with the current round `as`. Offline tests must exercise real same-round `{as, en_conf}` or a synthetic encrypt/decrypt vector; synthetic `as` alone is not enough to claim `en_conf` parity.

### PoW

`style.data.ext.p` drives PoW.

| Field | Meaning |
|---|---|
| `q["spin-0"]` | origin string |
| `m == "s"` | SHA1 |
| `m == "m"` | MD5 |
| `c` | number of leading zero hex chars |

Find `an` such that:

```text
hash(q[id] + an).substring(0, c) == "0" * c
```

Submit `p` as the result object, for example `{ "an": 3441, "t": 0 }` or a measured `t` value.

Field notes from live replay:

1. `t=0` is accepted in many warm sessions.
2. If `opp=3` appears after packaging looks correct, retry with measured wall-clock `t` before blaming angle.
3. Keep PoW bound to the same round's `ext.p`; never reuse `an` from a previous image.

### `ac_c`

For spin, the page submits a ratio, not raw degrees.

Source behavior:

```text
ac_c = Number((distance / (trackWidth - knobWidth)).toFixed(2))
```

Observed desktop values: `trackWidth ~= 290`, `knobWidth = 52`, denominator `238`. If a visual solver returns a correction angle in degrees, a practical mapping is:

```text
distance = (angle % 360) / 360 * 238
ac_c = round(distance / 238, 2)
```

Which is equivalent to:

```text
ac_c = round((angle % 360) / 360, 2)
```

Examples: `90° -> 0.25`, `180° -> 0.50`, `72° -> 0.20`.

Angle perception is the weak point. Treat image angle as a candidate; server `op` is the proof.

### Angle solver practice (validated live)

AI-generated circular images often produce false peaks at `0°/90°/180°/270°`. Recommended client strategy:

1. **Primary scorer**: horizontal Sobel energy inside a circular mask (fast, good default).
2. **Optional seeds**: contour `minAreaRect` / Hough line angles, then local refine.
3. **Top-k candidates** with 180° twin de-duplication; report confidence as gap to the next non-near peak.
4. **Never multi-submit** several angles on the same challenge / same `backstr` / same image.
5. After `op=3`, open a **fresh** `init/style/img` round.
6. **Reliability path**: if CV confidence is low or top-k exhausted, walk an `ac_c` grid on fresh rounds only, e.g. `0.00, 0.05, ..., 0.95` (step `0.05`, about 18°). Do not denser-grid the same challenge.
7. Save fail samples under `<projectRoot>/js_reverse_cache/samples/fail/` (`png` + redacted meta: `as`, `ac_c`, `angle`, `op`, `confidence`) for later CV tuning.

Protocol packaging can be correct while angle is wrong: an offline/live grid that hits `op=1` for some `ac_c` proves crypto/session; remaining work is perception.

### `rzData`

The first AES layer encrypts compact JSON of `rzData`.

Minimum useful shape:

```json
{
  "common": {
    "cl": [],
    "mv": [],
    "sc": [],
    "kb": [],
    "sb": [],
    "sd": [],
    "sm": [],
    "cr": {
      "screenTop": 0,
      "screenLeft": 0,
      "clientWidth": 1920,
      "clientHeight": 969,
      "screenWidth": 1920,
      "screenHeight": 1080,
      "availWidth": 1920,
      "availHeight": 1040,
      "outerWidth": 1920,
      "outerHeight": 1040,
      "scrollWidth": 1920,
      "scrollHeight": 2000
    },
    "simu": 0,
    "ac_c": 0
  },
  "backstr": "<style.backstr>",
  "captchalist": {
    "spin-0": {
      "ac_c": 0.81,
      "p": {"an": 3441, "t": 0},
      "cr": {"left": 700, "top": 200, "width": 360, "height": 360},
      "back": {"left": 755, "top": 255, "width": 250, "height": 250}
    }
  }
}
```

Notes:

1. `common.mv` should stay an empty list unless live evidence proves a track is required. Non-empty simulated motion has caused failures.
2. `common.cr` is a screen-info object, not an array.
3. `captchalist[id].cr` and `captchalist[id].back` come from `verifyScreen`; exact pixels are less important than including coherent geometry.
4. Prefer a `RoundState` object so `tk/as/backstr/en_conf/p/img` cannot be mixed across rounds.

### `fuid` and session cookies

1. `fuid` comes from `fingerprint.js` / `window.passFingerPrint()`, not from login identity cookies.
2. **Do not auto-map `ppfuid` -> `fuid`.** Wrong `fuid` can turn a working packaging path into repeated `op=3`.
3. Omit `fuid` unless the browser actually supplies it for the same product session, or the user passes an explicit value.
4. Live Python replay needs a real login session on `passport.baidu.com`:
   - minimum: `BAIDUID` + `BDUSS` (or `BDUSS_BFESS`)
   - often also: `STOKEN` / `PTOKEN` / `mkey` / `pplogid` / `ab_sr`
5. When loading Playwright / MCP `export_state` cookies into `requests`:
   - normalize shared auth cookies onto `.baidu.com` path `/`
   - also set passport-scoped copies for `BDUSS` / `STOKEN` / `PTOKEN` / `mkey` / `pplogid` when present
   - assert session before submit; if page bounced to login, re-login and re-export under `js_reverse_cache/private/**`
6. Cookie export files stay private. Sample network JSON outside `private/` must redact `Cookie` headers.

### `fs` Packaging

Source behavior:

```text
common_en = encryptMap(JSON.stringify(rzData), secondHandle)
fs = encryptMap(
  JSON.stringify({ common_en, backstr }),
  { key: newKey, as: currentAs, method: "aes-ecb" }
)
```

Where `newKey = getNewKey(currentAs)` after config update (`updateConfig` / init `as`).

Use compact JSON separators in Python to reduce accidental byte-shape differences. The final `/cap/log` form must include:

```text
_ refer ak as scene tk ver fs cv=submit typeid=spin-0 fuid=<optional>
```

Missing `cv=submit` or `typeid=spin-0` can produce `code=0` with no `op`, which is not a verification result.

## Replay Strategy

1. Export current browser state only under `<projectRoot>/js_reverse_cache/private/**` when live replay is approved.
2. Use Python `requests.Session` for final egress; browser/CDP is evidence only.
3. Run one fresh round per angle / `ac_c` attempt. After `op=3`, discard the round and fetch new `init/style/img`.
4. Default fast path: one round, no artificial sleep, no image write, coarse+refine OpenCV scan. Warm success can be ~0.6–1.0s.
5. Reliability path:
   - CV top-k on successive **fresh** rounds
   - then bounded `ac_c` grid on fresh rounds (`step=0.05` is enough; 0.20 has been observed as a live hit)
   - default `max_retries` about `8–12` for reliability, `3` for fast path
6. Optional short delay (`~300ms`) between failed rounds reduces noisy repeated `op=3` under burst traffic; do not invent long sleeps as “humanization”.
7. Do not repeatedly submit many guesses against the same challenge.

Recommended client control flow:

```text
open_round() -> score_image() -> pick_ac_c() -> pow() -> package_fs() -> submit
if op==1: success
if op is None: hard-fail packaging (cv/typeid)
if opp==3: stop / diff fs+session (limit 1-2 retries)
if op==2: surface multistep; do not pretend spin-only done
if op==3: save fail sample, fresh round, next candidate/grid
```

## Offline Fixture Schema

Keep redacted fixed vectors under `<projectRoot>/js_reverse_cache/samples/`.

Minimal same-round fixture:

```json
{
  "as": "<init.as>",
  "en_conf": "<style.ext.en_conf>",
  "p": {"q": {"spin-0": "..."}, "m": "s", "c": "3"},
  "backstr_len": 733,
  "secondHandle": {"method": "aes-ecb", "key": "", "custom": "", "as": "<init.as>"},
  "expect_pow_an": 681,
  "key16": "<getNewKey(as)>"
}
```

Capture with a `dump-fixture` style helper: open one live round, write fixture, **do not submit**. Never store raw cookies or full `backstr` in library cases; project-local samples may keep lengths / encrypted blobs only when needed.

Local proof should include fixed tests for:

1. `getNewKey(as)` including Keccak SHA3 cases.
2. AES-ECB ZeroPadding roundtrip and `en_conf` decrypt with empty-key fallback.
3. PoW result validation against `ext.p`.
4. `fs` double-layer decrypt sanity: outer contains `{common_en, backstr}`; inner contains `captchalist["spin-0"].ac_c`, `p`, `cr`, and `back`.
5. Optional live-captured `round_fixture.json` when available.

## Acceptance

Live proof, when approved, must show:

```text
code == 0 && data.op == 1
```

Record only redacted summaries such as `op`, `code`, `angle`, `ac_c`, `source` (`cv|grid`), `elapsed_ms`, `tk_len`, `ds_len`. Do not store raw cookies, raw account state, full private headers, or unsanitized session artifacts outside `js_reverse_cache/private/**`.

A pure `ac_c` grid that reaches `op=1` is valid evidence that packaging/session are correct even if CV is still weak.

## Failure Triage

| Symptom | First check |
|---|---|
| `code=0` but no `op` | request is telemetry; add `cv=submit` and `typeid=spin-0` |
| `op=3` | wrong angle/`ac_c` or stale/mixed round; refresh `init/style/img` before retry |
| many `op=3` but grid can still hit `op=1` | packaging OK; improve CV / use reliability grid |
| all `ac_c` grid fail | session/cookies/`ak`/`scene`/`fs` packaging, not OCR |
| `opp=3` or risk message | diff `fs` packaging, geometry, explicit `fuid`, and session state before blaming OCR |
| Empty or wrong `en_conf` decrypt | verify `getNewKey` and Keccak-vs-SHA3 implementation |
| Browser passes but Python does not | first verify request Cookie actually contains `BDUSS`; then form fields, JSON serialization, `rzData`, transport |
| Cookie export loads but submit still anonymous | domain/path normalization for `.baidu.com` / `.passport.baidu.com` |
| Auto `ppfuid` as `fuid` then worse | remove auto-map; omit `fuid` or use real fingerprint value |
| Slow runtime | remove artificial sleeps, skip image writes, use coarse+refine, keep retries bounded |

## Do Not

1. Do not treat every `/cap/log` as a verifier submit.
2. Do not accept `HTTP 200`, `code=0`, or `msg=Success` as success without `data.op == 1`.
3. Do not mix `tk/as/backstr/ext.p/image` from neighboring rounds.
4. Do not multi-guess the same challenge; always refresh after `op=3`.
5. Do not auto-inject `ppfuid` as `fuid`.
6. Do not mix `ak`/`scene` across login-wall and business security popups.
7. Do not store raw browser state or cookies outside the approved project root.
8. Do not ship browser-backed fetch as final delivery; Python owns final live egress.
