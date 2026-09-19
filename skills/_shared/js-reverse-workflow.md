# JS Reverse Workflow — Shared Contract

> 共享阶段、Handoff Envelope、Stage Gate 与 Evidence Storage 契约。
> 被 `../wechat-miniapp-reverse/SKILL.md`、`../trace/SKILL.md` 等跨 skill 引用。
> 本文件是占位契约：上游若提供完整版本，覆盖此文件即可。

## Stage（阶段）

| Stage | Owner surface | 产出 |
|---|---|---|
| `Observe` | 运行时 evidence owner（如 WMPF/AppService/WebView、浏览器 CDP） | 请求、响应、调用栈、脚本源码、断点 scope |
| `Capture` | 同上 | 完整请求样本、initiator、mutation point、cookie/token/header |
| `Transform` | `trace` / `iv8-web-reverse` / `nv8-env-patch` | 解混淆源码、env-patch、本地 JS 执行链 |
| `Rebuild` | `trace` pure-python-rebuild / `protocol-reverse` | browser-free Python 复现单请求 |
| `Patch` | `nv8-env-patch` | 本地 JS 环境补全 |
| `Consolidate` | `trace` collector | 稳定可复现的采集器 |
| `Port` | `trace` / 用户自定义 | 跨目标移植 |

Handoff 只能单调前进（Observe→Capture→Transform→Rebuild/Patch→Consolidate→Port），不得形成 browser/AST/miniapp 循环。

## Stage Gate Output

用户明确要求"只输出阶段门"时返回：

```json
{
  "MODE": "observe|capture|transform|rebuild|patch|consolidate|port",
  "OWNER": "wechat-miniapp-reverse|trace|iv8-web-reverse|nv8-env-patch|captcha-reverse",
  "NEXT_GATE": "下一阶段所需证据或条件",
  "REQUIRED_EVIDENCE": ["..."],
  "DO_NOT_USE": ["..."]
}
```

输出此格式时不启动 WMPFDebugger、不枚举 target、不取证。

## Handoff Envelope

跨 skill 转交时写 `js_reverse_cache/tasks/<task-id>/handoff.json`，逐字段保留：

- `task_id`：单调标识，贯穿 handoff 链。
- `revision`：packet revision，每次补证后递增。
- `primary_owner`：当前 stage 的 evidence owner skill 名。
- `next_stage`：单调前进的下一 stage。
- `scope` / `budget` / `retention`：scope 授权范围、时间预算、证据保留策略。
- `runtime_surface`：`wmpf-appservice` | `wmpf-webview` | `browser-chrome` | `browser-firefox` | `node-vm` | `iv8` | `nv8`。
- `target_url` / `target_method` / `target_fields`：目标请求的 URL、方法、关键字段名。
- `sample_input` / `sample_output`：样本请求与响应。
- `entry_script_url`：加密入口脚本 URL。
- `env_reads`：运行时读取的环境变量/全局。
- `evidence_ids`：引用的证据 ID 列表（见 Evidence Storage）。
- `success_predicate`：判定 handoff 完成的条件。
- `cookie scope` / `retention`：cookie 的域、有效期、保留策略。
- `artifacts`：已保存工件路径列表。
- 逐 ID 的 MCP `server`/`session`/`target`/`capturedAt`/`lifecycle`/`status`。

接收方缺证据时返回 `blocked-return`（带同一 `task_id`），原 owner 补证并递增 revision 重发。

## Checkpoint Fields (`skill_checkpoint`)

- 只写可复现的阶段状态与证据引用，不写原始敏感值。
- `lease_token`、`local.config.json` 内容、原始 cookie 值不写进 checkpoint。
- target switch / target 退出 / MCP 重连 / 资源释放 / lease 释放后，未重新验证的 request/script/frame/target ID 标 `stale` 或 `artifact-only`。

## Evidence Storage

证据落盘到执行项目的 `js_reverse_cache/tasks/<task-id>/`：

- `fixtures/`：原始请求/响应样本、HAR、脚本快照。
- `scripts.jsonl`：已保存的脚本源码索引（`save_script_source` 写入）。
- `handoff.json`：跨 skill handoff envelope。
- `handoff.json` 旁的子目录：大文件源码。

不写进 skill 目录（skill 是只读资产）。

## Routing Precedence

1. 运行环境优先于交付形式：目标在 WMPF/AppService/WebView → `wechat-miniapp-reverse` 拥有 runtime evidence，任何 CDP 浏览器家族只能做 methodology sidecar。
2. 普通 Web 页面 → `trace`（unknown family / browser-free collector）或 `js-reverse`（CDP 直调）。
3. 脱离浏览器复现 → `trace` pure-python-rebuild / `protocol-reverse` / `iv8-web-reverse` / `nv8-env-patch`。
4. 小程序内嵌验证码协议 → `captcha-reverse`（本仓库 `captcha-reverse` 未安装时回退 `trace` captcha profile）。

## ID Validity

跨 skill 不得直接消费另一个 MCP 的 request/script/frame/target ID。ID 只在 owner 内有效；转交后接收方重新建立自己的 ID 上下文，消费已保存且符合 retention 的样本工件。
