# CAPTCHA Routing

Use this profile when the task is an authorized CAPTCHA protocol chain, not ordinary OCR and not a generic API signer. The goal is a local protocol replay script with the same-round challenge, images, tokens, telemetry, dynamic parameters, and final server verify/check proof.

## Supported Families

| Family | Signals | Reference |
|---|---|---|
| GT3 slider | `register-slide`, `gettype.php`, `fullpage`, `slide`, `get.php`, `ajax.php`, `bg/fullbg/slice`, `validate/seccode` | `references/captcha/geetest-gt3-workflow.md` |
| GT4 | `captcha_id`, `lot_number`, `pow_detail`, `payload`, `process_token`, `/load`, `/verify`, `w`, `pow_msg`, `pow_sign` | `references/captcha/geetest-gt4-workflow.md` |
| Tencent TDC | `cap_union_prehandle`, dynamic `tdc.js`, `TDC.getData(true)`, `collect`, `eks`, `cap_union_new_verify` | `references/captcha/tencent-edgeone-tdc-workflow.md` |
| Yidun | `NECaptcha`, `c.dun.163.com/api/v3/get`, `/api/v3/check`, `cb`, `data`, `token`, front/bg images | `references/captcha/yidun-workflow.md` |
| Shumei | `captcha1.fengkongcloud.cn`, `/ca/v1/register`, `/ca/v2/fverify`, `captchaUuid`, `rid`, `fg/bg` | `references/captcha/shumei-workflow.md` |
| Yunpian | `captcha.yunpian.com`, `/v1/jsonp/captcha/get`, `/captcha/verify`, `captchaId`, `ypjsonp`, distance and points | `references/captcha/yunpian-workflow.md` |
| 360 Tianyu | `captcha.jiagu.360.cn`, `/api/v3/auth`, `/api/v3/check`, `360CaptchaSDK`, `captchaId`, `tracking` | `references/captcha/tianyu360-workflow.md` |
| Dingxiang/DX slider | `captcha.vivo.com.cn`, `/api/a`, `/api/p1`, `/api/p2`, `dingxiang-sdk.js`, `greenseer.js`, `_dx_app_*`, `_dx_captcha_vid` | This routing file; collect fresh evidence and use generic slider discipline |
| CSDN point-click | `embedded_captcha`, `click_v2`, prompt text, click coordinates, final verify | `references/captcha/csdn-point-click-workflow.md` |
| Ctrip captcha v4 | `captcha/v4`, `risk_inspect`, `verify_jigsaw`, `verify_icon`, encrypted verify payloads | `references/captcha/ctrip-captcha-v4-workflow.md` |
| Baidu Passport Spin V2 | `passport.baidu.com/cap/init`, `/cap/style`, `/cap/img`, `/cap/log`, `spin-0`, `backstr`, `ext.p`, `en_conf` | `references/captcha/baidu-passport-spin-v2-workflow.md` |

## Required State Discipline

1. Keep `get/load/prehandle/convert` outputs, images, cookies, challenge headers, random keys, telemetry, and final `verify/check` in the same session round.
2. Dynamic values must be generated from the current round: callback, POW, encrypted payload, track, elapsed time, token, and wrapper fields.
3. Browser automation is evidence only. Final delivery should be protocol replay plus local helper code.
4. Do not judge success by image recognition, token length, local `w` shape, or a generic success-looking HTTP status.
5. Parse JSONP before evaluating status fields.

## Image And Track Defaults

1. Slider tasks must separate original-image distance, rendered-page distance, submit distance, behavior track, and elapsed time.
2. Point-click tasks must separate prompt recognition, background object location, coordinate system mapping, and verify parameter generation.
3. GT4 `nine` answers are 0-based tile indexes converted to 1-based row/column pairs.
4. GT4 `icon` answers are ordered background centers mapped to `round(ratio * 10000)` coordinates.
5. OCR or external recognition can be used as a sub-step, but final proof is the server verify/check response.

## Optional Scripts

Allowed GT4 helper scripts are under `scripts/captcha/`. Treat them as examples and regression helpers, not universal drop-in bypasses. Re-check the current bundle, public key, field layout, image type, and server response before reuse.

## Excluded Public Profiles

Some publisher-reserved CAPTCHA profiles are intentionally absent from this public package. If the observed target only matches an absent profile, collect generic evidence with Trace core and report that the specialized workflow is not included.
