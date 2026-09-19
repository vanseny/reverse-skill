---
name: wechat-miniapp-reverse
description: >-
  【微信小程序任务优先】微信小程序 / WeChat Mini Program / WMPF 逆向调试。强触发关键词：微信小程序、PC微信小程序、WMPF、WeChatAppEx、AppService、WebView、127.0.0.1:62000、WMPFDebugger、小程序调试。使用 miniapp-reverse MCP 通过 CDP 调试端口分析小程序网络请求、源码、断点、调用栈和加密参数入口，是本套逆向 skill 体系里 WMPF runtime 的 `Observe`/`Capture` owner。WMPF/AppService/WebView 环境优先于“hook、Console、Snippets、调用栈、指纹”等交付词；只有普通 Web 页面 hook 才转 `trace` browser-hook profile。证据齐备后按目标转 `trace`（browser-free collector / AST / env-patch）、`iv8-web-reverse`、`nv8-env-patch` 或 `captcha-reverse`。不要用于普通 Web API 签名、Node.js 补环境、iv8 请求脚本、AST 解混淆或完整协议采集器。
argument-hint: "[小程序名称/目标行为/API关键词/加密参数]"
compatibility: "需要已注册的 miniapp-reverse MCP（pi ~/.pi/agent/mcp.json）；WMPFDebugger 依赖应已集成到 <WMPFDebugger_ROOT>/node_modules，不检查或安装 yarn/node_modules/frida"
---

# WeChat Miniapp Reverse

## 目标

使用本机 `miniapp-reverse` MCP 通过 WeChat Mini Program 的 CDP 调试端口，定位小程序里的网络请求、脚本源码、断点上下文、调用栈、Runtime 事件、Profiler 证据和 WebSocket 数据。

本 skill 是微信小程序运行时调试 skill，不是普通 Web 站点逆向 skill，也不是离线协议复现 skill。

共享阶段与 handoff 契约见 `../_shared/js-reverse-workflow.md`；本 skill 承担 WMPF 内的 `Observe` 和 `Capture`，`Transform` 之后的阶段交给 `trace`、`iv8-web-reverse`、`nv8-env-patch` 或 `captcha-reverse`。若用户明确要求“只输出阶段门”，按该文件的 Stage-Gate Output 返回 `MODE`、`OWNER`、`NEXT_GATE`、`REQUIRED_EVIDENCE` 和 `DO_NOT_USE`，不要启动 WMPFDebugger、不枚举 target、不取证。`skill_checkpoint` 字段规则见同文件 Checkpoint Fields；lease token、`local.config.json` 内容和原始 cookie 值不写进 checkpoint。

## 工具调用形式

本机 MCP server 名为 `miniapp-reverse`（注册在 `~/.pi/agent/mcp.json`，命令指向 `<WMPFDebugger_ROOT>\miniapp-reverse-mcp\run_mcp_server.py`）。所有调试能力通过

```text
mcp_call_tool(server="miniapp-reverse", tool="<tool>", arguments={...})
```

调用；需要确认当前工具集或参数 schema 时用 `mcp_list_tools(server="miniapp-reverse")`、`mcp_list_tools(server="miniapp-reverse", tool="<tool>")`，进程状态用 `mcp_status`。下文为简洁写作 `miniapp-reverse/<tool>(参数)`，它不是独立工具名，实际一律走 `mcp_call_tool`，括号内参数即 `arguments` 字段；Python 风格的 `True` 在 `arguments` 里写 JSON `true`。

MCP 未注册或进程异常时，说明需要重启 pi 或用 `mcp_stop_server(server="miniapp-reverse")` 后重试；不用浏览器系 MCP（`js-reverse`、`chrome-devtools`、`camoufox-reverse`、`frx-director`）冒充小程序调试能力。

## 快速目标闸门

启动或枚举 target 前，先判断用户给的是哪类目标：

| 用户输入 | 动作 |
|---|---|
| 只说小程序名称/打开方式 | 只确认 WMPFDebugger 服务和 DevTools URL，等待业务动作 |
| 给了 API 关键词、字段名、请求样本或具体点击动作 | 建 target 上下文后按网络/源码/断点链路分析 |
| 已经有请求、调用栈和参数证据，目标是脱离微信复现 | 清理断点、释放 lease 后转 `trace`（未知多层/纯协议 collector）或 `iv8-web-reverse`（明确 Python + iv8） |
| 普通 Web 站点 URL | 未知家族或完整 collector 转 `trace`；确认 Akamai 转 `akamai-protocol-reverse`；完整验证码协议转 `captcha-reverse` |

没有字段、API、请求样本或业务动作时，不盲抓网络、不保存源码、不下断点。

## 跨 Skill 所有权与交接

本 skill 是 WeChat/WMPF 的唯一 runtime evidence owner，优先级高于任何 CDP 浏览器家族（`js-reverse` Edge、`chrome-devtools`、Camoufox）。跨 skill 时按 `../_shared/js-reverse-workflow.md` 的 Handoff Envelope 与 Stage Fields 写 `js_reverse_cache/tasks/<task-id>/handoff.json`，并在 `runtime_surface` 标 `wmpf-appservice` 或 `wmpf-webview`；不得输出只有 URL/request id 的缩减 packet。

- 在 miniapp 工具前发现目标其实是普通 Web，才允许 discover route correction。建立 WMPF target 后不得横向转另一个 browser owner；浏览器家族只能提供 methodology sidecar，不能接管 AppService/WebView runtime。
- 运行环境优先于交付形式：用户即使要求“给 Console/Snippets hook”，只要目标位于 WMPF/AppService/WebView，仍由本 skill 建立 target、execution context 和证据边界。`trace` browser-hook profile 只能在 target 与观察点已知后提供 snippet sidecar，不拥有 miniapp runtime，也不得输出普通页面 `window.fetch`/`XMLHttpRequest` hook 冒充 AppService 方案。
- full handoff 只可单调前进到 `Transform`、`Rebuild`、`Patch`、`Consolidate` 或 `Port`。接收方缺证据时应带同一 `task_id` 返回 `blocked-return`，本 skill 补证并递增 packet revision 重发，不能形成 miniapp/browser/AST 循环。
- packet 必须逐字段保留 shared contract 要求的内容，尤其是 `target_url`/`target_method`/`target_fields`、`sample_input`/`sample_output`、`entry_script_url`、`env_reads`、`runtime_surface`，以及每个 WMPF ID 的 MCP server/session/target/`capturedAt`/lifecycle/status、cookie scope 与 retention、`artifacts` 路径。
- target switch、target 退出、MCP 重连、资源释放或 WMPF lease 释放后，未重新验证的 request/script/frame/target ID 标 `stale` 或 `artifact-only`。其它 MCP 不得调用 miniapp ID；只能消费已保存且符合 retention 的样本。

## 触发边界

使用本 skill 当用户提到以下任一目标：

- 微信小程序、PC 微信小程序、微信开发者工具小程序、WMPF、WeChatAppEx、AppService、WebView。
- 需要抓小程序 XHR/Fetch/WebSocket 请求、响应体、POST body、请求 initiator、调用栈、ExtraInfo、失败原因。
- 需要在小程序 JS 源码里搜索函数/参数、读取脚本片段、保存脚本源码。
- 需要在小程序运行时设置 XHR 断点或文本断点，查看 paused scope 变量。
- 需要捕获 Runtime console/exception/context，或用 CPU Profiler/coverage 定位热点函数和执行脚本。
- 需要设置 DOM event listener breakpoint 分析点击、输入、提交等事件入口。
- 需要切换 AppService/WebView target 来分析逻辑层或渲染层。
- 用户给的是小程序页面行为、接口关键词、加密参数名，但没有普通浏览器页面 URL。
- 目标明确是 WMPF/AppService/WebView 中的 hook、Console 或 Snippets；这些交付词不能覆盖小程序 runtime 所有权。

不要使用本 skill：

- 普通 Web 页面/API 签名、反爬、挑战页、浏览器环境指纹逆向 → `trace`（未知家族、多层链路或 browser-free collector），确认 Akamai 家族 → `akamai-protocol-reverse`。
- 普通 Web 页面只要一段 Console/Snippets hook 脚本 → `trace` browser-hook profile；WMPF/AppService/WebView hook 仍留在本 skill。
- 已有 JS 入口，要在 Node.js/vm 中补环境跑通 → `trace` env-patch profile；用户明确指定 nv8 → `nv8-env-patch`。
- 明确要 Python + iv8 + requests 脚本 → `iv8-web-reverse`。
- 整文件 AST 解混淆、控制流还原 → `trace` AST profile。
- 小程序内嵌验证码的完整协议链（challenge → 图片/轨迹/PoW → verify/check）→ `captcha-reverse`；本 skill 只提供 WMPF 内的请求、源码和断点证据。验证码识别模型训练 → `captcha-vision`。
- 普通 Web 瑞数/Ruishu/Rivers 任务不属于小程序调试 → 未知或完整目标转 `trace`；已确认 Reese84 采集器/回放转 `iv8-web-reverse`。

## 启动前置

不要检查或安装 WMPFDebugger 的 yarn、`node_modules`、frida 等依赖；这些依赖应已集成在用户本机的 `<WMPFDebugger_ROOT>/node_modules`。

本前置流程先检查 WMPFDebugger 调试服务状态；未运行时启动，已由脚本管理时仍通过启动命令获取或复用本任务 lease，外部未知监听者则只验证、不接管。

先定位 `<WMPFDebugger_ROOT>`，不要写死机器路径；优先复用本机缓存：

1. 先读取本 skill 目录下的 `local.config.json`。只有目录同时满足这些指纹才复用：`package.json.name=WMPFDebugger`、`main=src/index.ts`、声明 `frida/protobufjs/ws/ts-node`、存在 `src/index.ts` 和本地 `node_modules/.bin/ts-node.cmd`，且入口源码包含 WMPFDebugger 的 CLI/WebSocket 标记。
2. 如果缓存不存在或校验失败，再用同一组强指纹检查当前工作目录本身；普通 TypeScript 项目即使也有 `src/index.ts` 和 `node_modules/`，也不得被认作 WMPFDebugger。
3. 否则用同一组强指纹检查当前工作目录的父目录，以及父目录下名为 `WMPFDebugger` 的兄弟目录。
4. 如果仍找不到，向用户问一句：`WMPFDebugger 根目录在哪里？`，不要猜测固定盘符路径。
5. 用户提供路径后仍执行完整强指纹校验；校验通过才写入本 skill 目录下的 `local.config.json`，格式为 `{ "wmpfDebuggerRoot": "..." }`，后续启动直接复用。

`scripts/wmpf-debugger-service.ps1` 已内置同样的 root 定位顺序；首次运行没有 `local.config.json` 时可以不传 `-Root`，找不到 root 才会返回需要询问用户的提示。
`local.config.json` 是本机私有缓存，可能包含用户机器上的绝对路径；只在定位 WMPFDebugger root 时读取或覆盖该缓存项。启动器还会在 `%LOCALAPPDATA%\pi\wechat-miniapp-reverse\wmpf-debugger-state.json` 记录由该启动器管理的 launcher PID、进程启动时间、root 和任务 lease，用于证明进程归属并避免一个任务停止另一个任务仍在使用的服务；root 解析和生命周期操作在命名互斥锁 `Local\Pi.WechatMiniappReverse.WmpfDebuggerService` 内串行化。改动 state 路径或互斥锁名前必须先释放所有 lease、确认 9421/62000 已不再监听，否则旧 state 会失联只能人工清理。不要在最终报告、README、test prompt、benchmark 结果或打包产物中展开这两个文件的完整内容或路径值；分发、同步或公开分享本 skill 前必须确认 `local.config.json` 已被排除。root 必须是本地盘路径，不接受 CMD 无法可靠设为工作目录的 UNC 路径。
启动脚本会隐藏长期运行的后台窗口，只把输出写入 `<WMPFDebugger_ROOT>\wmpf-debugger.log`；如果看到无信息黑窗口，优先检查是否绕过脚本直接运行了 raw `cmd`/`start` 命令。

本地资源索引：`scripts/wmpf-debugger-service.ps1` 是唯一入口（`-Action Start|Status|Stop`），负责 root 校验、state/lease、端口与进程树归属；`scripts/start-wmpf-debugger.cmd` 和 `scripts/stop-wmpf-debugger.cmd <lease-token>` 只是给用户终端的 cmd 包装，停止时只释放调用任务的 lease，最后一个 lease 才停止精确匹配的进程树；`scripts/resolve-wmpf-root.ps1` 只做强指纹校验与缓存写入；`local.config.json` 只缓存本机 `wmpfDebuggerRoot`；`<WMPFDebugger_ROOT>\wmpf-debugger.log` 只用于短探测 ready 状态或排查启动失败。

每次使用 `miniapp-reverse` MCP 前，先确认 WMPFDebugger 调试服务是否已启动，但不要在用户打开小程序前抢跑 target 枚举：

1. 如果近期没有服务状态证据，先调用 `scripts/wmpf-debugger-service.ps1 -Action Status` 做只读检查：0 表示该启动器管理的服务 ready/starting，3 表示未运行，4 表示 9421/62000 有未纳入 state 的监听者，6 表示另一个生命周期操作持锁超时。code 6 只在 250~500 ms 后重试一次；仍为 6 就报告“另一个生命周期操作仍在进行”并停止，不并发绕过互斥锁。只有用户明确说明已有外部 WMPFDebugger，或需要验证 code 4 的监听者是否真是可用服务时，才用一次 `miniapp-reverse/list_targets()` 区分“可用但暂无 target”和“端口冲突”；不要把 target 枚举当默认端口探针。
2. 当前任务要使用由脚本管理的服务时，无论 Status 是 0 还是 3，都调一次 `-Action Start`（可带 `-Root` 和已有 `-LeaseToken`）获取或复用本任务 lease，并记录输出的 `WMPFDebugger lease token`（只留在任务上下文，不写进报告和 checkpoint）。启动器只接受 state 对应的进程树；9421/62000 被无法证明归属的 PID 占用时返回 4，必须报告冲突 PID 并停止，不能把未知监听者冒充成 WMPFDebugger。不要把 raw `start` 命令直接放进当前工具调用，除非用户要求在自己的终端手动执行；不要追加 `&& ping`、`timeout`、`tail -f`、持续 `type` 日志或任何长轮询等待。
3. 启动后最多做 2 次短探测：用 `bash` 的 `grep`/`tail` 查 `wmpf-debugger.log` 中的 `proxy server running` 或 `you can now open any miniapps`，或用一次短超时端口检查（`netstat -ano | grep -E "62000|9421"`）；总等待预算控制在 5 秒以内。看到 ready 日志后，立即停止进一步 target/network MCP 调用，提示用户先打开/重新打开目标小程序；5 秒内未 ready 时，报告日志路径并让用户稍后重试，不要继续卡住当前回合。
4. 只有用户明确说“已打开”、已经给出目标小程序正在运行、或已经触发了目标行为后，才调用 `miniapp-reverse/list_targets()` 建立 target 上下文。
5. 如果服务已启动但 `list_targets` 超时，不要反复重试堵塞；说明“服务已启动，等待目标小程序接入”，让用户重新打开小程序后再枚举。

推荐启动命令（pi 的 `bash` 工具里直接调 PowerShell 服务脚本，能立即返回当前工具调用）：

```bash
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "<SKILL_DIR>/scripts/wmpf-debugger-service.ps1" -Action Start -Root "<WMPFDebugger_ROOT>"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "<SKILL_DIR>/scripts/wmpf-debugger-service.ps1" -Action Status
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "<SKILL_DIR>/scripts/wmpf-debugger-service.ps1" -Action Stop -LeaseToken "<lease-token>"
```

已有 lease 要复用时加 `-LeaseToken "<已有lease-token>"`；不传 `-Root` 时脚本会按 `local.config.json`、当前目录、父目录和兄弟 `WMPFDebugger` 目录自动定位。

**不要在 pi 的 `bash` 工具里转发 `.cmd` 包装脚本。** 实测：git bash 下 `cmd //c "call scripts\start-wmpf-debugger.cmd \"<root>\""` 会丢掉 `%~1`，脚本拿不到 root，返回码 2 并报 `The supplied path is not a valid WMPFDebugger root.`——看起来像路径无效，实际是 shell 传参丢失；同一路径直调 PowerShell 脚本能通过强指纹校验。遇到码 2 先换成 PowerShell 直调重试，确认不是传参问题后再怀疑 root 本身。

`scripts\start-wmpf-debugger.cmd ["<WMPFDebugger_ROOT>"] ["<已有lease-token>"]` 和 `scripts\stop-wmpf-debugger.cmd "<lease-token>"` 只用于用户自己的 cmd/PowerShell 终端（在 cmd 里必须用 `call`）；只传 token 时第一个位置参数给空字符串。

退出码含义：`0` 成功；`1` 启动中退出（查日志）；`2` root 未通过强指纹校验或传参丢失；`3` 未运行；`4` 端口有无法证明归属的监听者（报冲突 PID 并停止，不按端口杀）；`5` 另一个 root 的受管服务在跑；`6` 生命周期锁超时（只重试一次）；`7` lease token 缺失/无效/不拥有该服务。

不要在 `SKILL.md` 中写死某台机器上的绝对路径；运行时用本 skill 的实际 base directory 拼接 `scripts/`。

如果用户坚持手动启动，只建议用户在自己的独立终端执行等价命令；助手不要把 raw `start` 命令作为工具调用运行。需要实时看日志时，另开终端读取 `<WMPFDebugger_ROOT>\wmpf-debugger.log`，不要把长期运行服务或日志跟随挂在当前 `bash`/shell 工具调用里。

连接成功后的 UI 快路径：一旦 `miniapp-reverse/list_targets()` 成功返回 target，直接把 `devtools://devtools/bundled/inspector.html?ws=127.0.0.1:62000` 发给用户自行打开。不要调用浏览器 MCP 的 new_page/导航工具打开普通 Chrome 页面，不要检测 `about:blank`，不要追问“是否看到 UI”。只有用户明确说链接打不开时，才给出系统浏览器兜底命令或让用户手动复制 URL。如果用户尚未给字段、API、请求样本或业务动作，发出链接后停止并询问；如果原请求已经给出明确目标，就直接进入对应工具链，不重复确认。

目标确认闸门：用户没有给字段、API、请求样本或明确业务动作前，不要自动盲抓网络、切换多个 target、搜索源码、保存脚本或下断点。允许做的仅限于确认服务、确认 target、打开 UI、报告当前状态和等待用户目标。

工作目录：

```text
<WMPFDebugger_ROOT>
```

## 能力矩阵

按用户目标选择工具，不要只按清单顺序机械调用：

| 用户目标 | 首选工具链 | 关键参数/停止条件 |
|---|---|---|
| 确认服务和 target | `miniapp-reverse/list_targets` → `miniapp-reverse/switch_target` | 多 target 时先让用户确认 AppService/WebView；选定后停止切换 |
| 打开调试界面 | 直接输出 DevTools URL | 不调用浏览器 MCP；用户明确说打不开时才给兜底命令 |
| 抓取目标请求 | `miniapp-reverse/list_network_requests` | 先用 `include_preserved_requests=true` 查历史保留请求，再用 `wait_ms=1000~5000` 等实时请求；有接口关键词/域名/路径时必须先带 `url_filter`；默认只返回最新 20 条，用 `page_idx` 翻页，不要把第一页当全量 |
| 查看请求详情/响应 | `miniapp-reverse/list_network_requests(reqid=...)` → `miniapp-reverse/get_response_body` | 响应为空或未完成时检查 `loadingFailed` / preserved 请求，再让用户重新触发行为 |
| 获取 POST body | `miniapp-reverse/get_request_post_data` | 当列表里的 request body 被截断、缺失或需要 CDP 原始 POST 数据时使用；超过 20000 字节的 body 要调高 `max_size` |
| 判断请求失败原因 | `miniapp-reverse/list_network_requests(reqid=...)` | 优先看 ExtraInfo、`loadingFailed.failure`、blocked/cors/canceled 证据，不凭状态码猜测 |
| 找请求入口调用栈 | `miniapp-reverse/get_request_initiator` → `miniapp-reverse/get_script_source` | 有 URL/line/column 后读取上下文，不急着下断点 |
| 搜索参数或函数 | `miniapp-reverse/list_scripts` → `miniapp-reverse/search_in_sources` → `miniapp-reverse/get_script_source` | 搜索顺序：接口路径 → 参数名 → header → 函数名 → 业务词；必须显式传 `exclude_minified=false`，否则默认跳过小程序的压缩主包 |
| 保存大脚本 | `miniapp-reverse/save_script_source` | `file_path` 必填（写到 `js_reverse_cache/tasks/<task-id>/`），配 `script_id` 或 `url`；写文件前说明保存路径和原因，当前请求已明确要求保存时不重复确认 |
| XHR 断点 | `miniapp-reverse/break_on_xhr` → 触发行为 → `miniapp-reverse/get_paused_info` | URL 片段要尽量窄；命中后先看 scope/stack |
| DOM 事件入口 | `miniapp-reverse/set_event_listener_breakpoint` → 触发事件 → `miniapp-reverse/get_paused_info` | 适合 click/input/submit/key*，命中后及时 resume 并清理 |
| 代码文本断点 | `miniapp-reverse/get_script_source` → `miniapp-reverse/set_breakpoint_on_text` | 只对函数体内部具体语句下断点，不对函数名/赋值语句下断点；高频语句用 `condition` 收窄命中条件 |
| paused 求值/单步 | `miniapp-reverse/evaluate_script` → `miniapp-reverse/step` → `miniapp-reverse/resume_execution` | 优先在当前 `frame_index` 求值；分析完及时 resume |
| 断点盘点/清理 | `miniapp-reverse/list_breakpoints` → `miniapp-reverse/remove_breakpoints` | 换 target、任务结束或跑偏前先清理；当前处于 paused 只想继续执行时用 `resume_execution`，不要用 `remove_breakpoints` 代替；只删单个 XHR 断点用 `xhr_url` |
| Runtime 事件 | `miniapp-reverse/get_runtime_events` | `event_type` 选 `console` / `exception` / `context`；异常先看堆栈和 executionContext |
| CPU 热点定位 | `miniapp-reverse/start_cpu_profile` → 触发行为 → `miniapp-reverse/stop_cpu_profile` | 用于 JSVMP 循环、签名函数热点、重型计算入口；不要长时间开启 |
| 覆盖率定位 | `miniapp-reverse/precise_coverage(action='start'|'take'|'stop')` | 触发目标行为后看哪些脚本/函数实际执行 |
| WebSocket 分析 | `miniapp-reverse/get_websocket_messages` | 先列连接，再看 handshake、frame error；用 `wsid`、`direction`、`show_content=true` 看内容；默认每页 10 条，用 `page_idx` 翻页 |
| 资源释放 | `miniapp-reverse/resume_execution` → `miniapp-reverse/list_breakpoints` → `miniapp-reverse/remove_breakpoints(clear_all=true)` → 必要时 `-Action Stop -LeaseToken "<lease-token>"` | 代码落地并拿到 response、最终报告可完整复现请求链路、换任务、异常中止或结束前必须执行 |

## 关键参数与默认值陷阱

这些默认值会安静地丢证据，先读再调工具：

| 工具 | 陷阱 | 做法 |
|---|---|---|
| `search_in_sources` | `exclude_minified` 默认 `true`，而小程序主包几乎全是压缩单行文件 | 找签名/加密参数必须 `exclude_minified=false`；结果太多时用 `url_filter` 收窄、`max_results` 提上限、`max_line_length` 看更长上下文；正则用 `is_regex=true` |
| `get_script_source` | `length` 默认 1000，压缩单行文件用 `start_line/end_line` 只能拿到一整行 | 压缩文件用 `offset` + `length` 滑窗取上下文；普通文件用行区间；优先用 `url` 而不是 `script_id` |
| `list_network_requests` | 首次调用才会连 `endpoint`、attach target 并开 Network；默认 newest-first、`page_size=20` | 首次就带 `url_filter`；历史请求靠 `include_preserved_requests=true`；翻页用 `page_idx`；`clear_existing=true` 会丢已抓缓存，只在确认要重新开局时用 |
| `get_paused_info` | `max_scope_depth` 默认 2，深层闭包里的密钥/中间值看不到 | 需要时提高 `max_scope_depth`，换栈帧用 `frame_index` |
| `evaluate_script` | `return_by_value` 和 `await_promise` 默认 `true`，大对象/不可序列化对象会失败 | 先用表达式收窄到字段或 `typeof`/`Object.keys`；paused 时自动在当前 frame 求值，换帧用 `frame_index` |
| `get_request_post_data` | `max_size` 默认 20000 | 大 body 调高后重取，不要拿截断值当完整请求体 |
| `stop_cpu_profile` / `get_runtime_events` / `precise_coverage` | 默认只给摘要（`include_profile=false`、`limit`有上限） | 先看摘要定位热点，确实需要完整采样才开 `include_profile=true`；`get_runtime_events` 用 `clear=true` 分隔两次触发 |
| `remove_breakpoints` | 它是删断点，不是继续执行 | paused 下想让代码跑下去用 `resume_execution`；收尾才 `clear_all=true` |

## 标准工作流

| 步骤 | 目标 | 关键工具 | 产出 |
|------|------|---------|------|
| 1 | 建立目标上下文 | `list_targets` → `switch_target` | 选定 AppService 或 WebView |
| 2 | 观察网络请求 | `list_network_requests` | 目标请求 reqid + 参数/响应 |
| 3 | 搜索源码 | `list_scripts` → `search_in_sources` | 函数/参数所在脚本 URL + 行号 |
| 4 | 断点调试 | `break_on_xhr` / `set_breakpoint_on_text` | 调用栈 + scope 变量 |
| 5 | Runtime/Profiler | `get_runtime_events` / `start_cpu_profile` | 热点函数、异常、console |
| 6 | WebSocket | `get_websocket_messages` | 连接 + 消息内容 |
| 7 | 资源释放 | `resume_execution` → `remove_breakpoints` → `-Action Stop -LeaseToken "<lease-token>"` | 清理每个 target；正常、异常或转交退出都释放本任务 lease |

### 1. 建立目标上下文

仅在用户已经打开目标小程序后调用：

- `miniapp-reverse/list_targets()`：列出 AppService/WebView 目标，确认当前选中 target；记录本任务访问过的 target id。
- 如默认 target 不对，调用 `miniapp-reverse/switch_target(target_id=...)`。切换前先清理当前 target 的 paused/断点/profiler/coverage 状态；不得把清理责任留到另一个 target。
- target 成功返回后，直接输出 DevTools URL，不要调用浏览器工具打开 UI，也不要检测 UI 状态。
- 原请求尚无字段、API、请求样本或业务动作时才询问要抓什么并等待；已有明确目标时直接进入对应网络/源码链路。

向用户简要说明当前分析的是 AppService 还是 WebView；仅在目标类型或业务动作仍有歧义时等待确认。

### 2. 观察网络请求

常规入口：

- 只有用户给了字段、API URL、请求/响应样本或明确业务动作后，才开始抓包、切 target、搜索源码或设置断点。
- 如果用户给了接口 URL、域名、路径、参数名或业务关键词，先用 `miniapp-reverse/list_network_requests(include_preserved_requests=true, url_filter=关键词, wait_ms=0~1000)` 查历史保留请求。
- 如果用户没有给关键词，先问一句目标动作或接口关键词；仍可用 `include_preserved_requests=true` 粗看最近请求，但不要只盯实时空缓冲区。
- 历史没有命中时，再提示用户重新触发目标动作，并用 `miniapp-reverse/list_network_requests(wait_ms=1000~5000, url_filter=关键词)` 等实时请求。
- 用 `reqid` 查看单条请求详情。
- 用 `miniapp-reverse/get_response_body(request_id=...)` 获取响应体。
- 请求 body 不完整或需要 CDP 原始 POST 数据时，用 `miniapp-reverse/get_request_post_data(request_id=...)`。
- 请求失败、CORS、blocked、cancelled 或状态异常时，先查看单条请求详情里的 ExtraInfo 和 `loadingFailed`，再判断是否需要切 target 或重放行为。
- 用 `miniapp-reverse/get_request_initiator(request_id=...)` 找发起调用栈。

如果实时没有请求，不要立刻判定“没有请求”；先检查 preserved 请求、切换 AppService/WebView target、再让用户复现目标动作。只有这些都无结果时，再进入源码关键词搜索。

### 3. 定位脚本与入口

使用：

- `miniapp-reverse/list_scripts(url_filter=...)`：列脚本。
- `miniapp-reverse/search_in_sources(query=..., exclude_minified=false)`：搜索关键词、接口路径、参数名、函数名；不传 `exclude_minified=false` 会默认跳过压缩主包。
- `miniapp-reverse/get_script_source(url=..., offset=..., length=...)`：读取命中上下文；压缩单行文件用 `offset`+`length` 滑窗，普通文件用 `start_line`/`end_line`。
- `miniapp-reverse/save_script_source(...)`：只在需要整包或大文件时保存源码到用户工作区。落盘位置遵循 `../_shared/js-reverse-workflow.md` 的 Evidence Storage：写到执行项目的 `js_reverse_cache/tasks/<task-id>/`（源码进 `fixtures/` 或 `scripts.jsonl` 旁的子目录），不写进本 skill 目录。

搜索优先级：接口路径片段 → 参数名 → header 名 → 加密函数名 → 业务关键词。

### 4. 动态断点分析

设置断点前先读取函数体上下文，不要直接在函数名或赋值语句上下断点。

可用工具：

- `miniapp-reverse/break_on_xhr(url=...)`：按接口 URL 片段打 XHR/Fetch 断点。
- `miniapp-reverse/set_event_listener_breakpoint(event_name=..., target_name=...)`：按 DOM 事件入口打断点，如 `click`、`input`、`submit`、`keydown`。
- `miniapp-reverse/remove_event_listener_breakpoint(event_name=..., target_name=...)`：移除 DOM 事件入口断点。
- `miniapp-reverse/set_breakpoint_on_text(text=..., condition=...)`：对函数体内部具体语句打文本断点；高频语句用 `condition` 只在目标条件下命中。
- `miniapp-reverse/list_breakpoints()`：查看当前 XHR/代码断点，避免重复设置或漏清理。
- `miniapp-reverse/get_paused_info(include_scopes=true, max_scope_depth=...)`：查看调用栈和局部变量；深层闭包要调高 `max_scope_depth`（默认 2）。
- `miniapp-reverse/evaluate_script(expression=..., frame_index=...)`：在 paused frame 中求值。
- `miniapp-reverse/step(action="over"|"into"|"out")`：单步。
- `miniapp-reverse/resume_execution()`：恢复执行。
- `miniapp-reverse/remove_breakpoints(clear_all=true)`：任务结束或换目标前清理断点（它不是“继续执行”，paused 下用 `resume_execution`）。

### 5. Runtime 与 Profiler 证据

用于网络/源码定位不够直接时补强运行时证据：

- `miniapp-reverse/get_runtime_events(event_type="console"|"exception"|"context")`：查看 console、异常和 execution context。
- `miniapp-reverse/start_cpu_profile()`：开始 CPU 采样，随后让用户触发目标动作。
- `miniapp-reverse/stop_cpu_profile(limit=...)`：停止采样并查看热点函数、脚本 URL、行列号。
- `miniapp-reverse/precise_coverage(action="start")`：开始覆盖率采集。
- `miniapp-reverse/precise_coverage(action="take"|"stop")`：查看目标动作实际执行过的脚本。

Profiler/coverage 不替代调用栈和断点；它们用于缩小搜索范围，拿到脚本 URL/行列号后仍回到源码上下文或断点验证。

### 6. WebSocket 分析

使用：

- `miniapp-reverse/get_websocket_messages()`：列连接。
- `miniapp-reverse/get_websocket_messages(wsid=..., show_content=true)`：看消息。
- 列连接和查看单连接时优先看 handshake request/response headers、状态码和 frame error，再分析 payload。
- 用 `direction="sent"` 或 `direction="received"` 分离上下行。

### 7. 资源释放

满足任一条件时必须释放资源：用户代码已经落地并能实际拿到 response 响应数据；已经给出最终分析报告且可基于报告完整复现请求链路；用户要求结束/换目标/换 skill；当前任务需要转交 `trace`、`iv8-web-reverse`、`nv8-env-patch` 或 `captcha-reverse` 继续实现。

释放顺序：

- 对本任务访问过的每个 target 逐一切回并执行清理；如果某个 target 已关闭、无法再切换，记录“target 已退出，无法清理其内存态”并继续清理其余 target，不因单个消失 target 中断收尾。如果当前 paused，先调用 `miniapp-reverse/resume_execution()` 恢复执行。
- 调用 `miniapp-reverse/list_breakpoints()` 查看残留断点。
- 如存在断点，调用 `miniapp-reverse/remove_breakpoints(clear_all=true)` 清理所有 XHR/代码断点。
- 如设置过 DOM event listener breakpoint，调用 `miniapp-reverse/remove_event_listener_breakpoint(...)` 清理事件断点。
- 如开启过 CPU profiler 或 precise coverage，分别调用 `miniapp-reverse/stop_cpu_profile()` 或 `miniapp-reverse/precise_coverage(action="stop")` 停止采集。
- 不再保留会影响后续小程序运行状态的断点、paused 状态或临时 target 切换假设。
- 如果当前任务已记录 lease token，且已经代码落地拿到 response、最终报告可完整复现链路、用户要求结束或任务转交完成，必须执行 `-Action Stop -LeaseToken "<lease-token>"`（pi 里直接调 `scripts/wmpf-debugger-service.ps1`）释放本任务 lease；仍有其他 lease 时保留服务，最后一个 lease 才逐个校验 launcher/子进程 PID 与启动时间后终止，不使用按端口或可复用父 PID 的 `/T` 杀树，不再额外等待用户确认。退出码 `7` 表示 token 缺失/无效/不拥有该服务，`4` 表示端口上有无法证明归属的监听者：两种都只报告，不改成按端口杀进程。
- 获取 lease 后即使 MCP 不可用、目标消失、设置失败、用户取消或分析异常中止，也要在退出当前任务前执行同一 lease 释放步骤；停止脚本自身失败时在内部任务上下文保留 token 供重试，最终报告只说明“lease/state 未释放”和失败原因，不展开原始 token 或 state 内容，也不伪称已释放。
- 如果 agent/终端硬崩溃而未能释放 lease，不按 TTL 自动回收，避免误停其他任务；恢复会话后使用原 token 释放，原 token 已丢失时保留 state 并让用户决定人工维护，不删除 state、不按端口杀进程。
- 如果 WMPFDebugger 服务是用户原本已启动的，只清理 MCP 调试状态，不主动关闭用户进程；除非用户明确要求停止服务。
- 停止脚本没有有效 state 或 state 已陈旧但端口仍有监听者，或者端口包含不属于该 launcher 进程树的 PID 时，必须拒绝终止并返回错误码 4；如果没有 state 且端口也没有监听者，可作为幂等 no-op 返回成功。报告冲突，不得改成按端口杀进程。
- 停止后用一次短端口检查确认 `62000` 不再 LISTENING，并在最终报告写明 DevTools URL 已不可访问或服务仍由用户保留。

## 异常与确认

遇到下面情况时，不要盲目继续：

- `miniapp-reverse` MCP 工具不可用或启动失败：先用 `mcp_status` 确认进程状态，再说明 MCP 未就绪、需要重启 pi 或 `mcp_stop_server` 后重试；不要改用普通 Web 逆向 MCP 冒充微信小程序调试能力。
- `127.0.0.1:62000` 连接失败：只启动 WMPFDebugger 调试服务；不要检查或安装 WMPFDebugger 依赖；启动必须用 `scripts/wmpf-debugger-service.ps1 -Action Start`（pi 里直接调 PowerShell），避开 `start /B`、raw `start` 工具调用、git bash 转发 `.cmd`，也不要直接跑 `npx ts-node src/index.ts` 卡住工具调用。
- 启动服务时弹出无信息黑窗口：说明可能没有用隐藏窗口的服务脚本，后续必须改用 `-Action Start`；不要为了看日志保留黑窗口，日志统一查看 `wmpf-debugger.log`。
- 启动服务后等待过久：立即停止继续等待，改为短探测日志/端口并向用户说明当前状态；不要为了“确认 ready”而让工具调用阻塞超过 5 秒。
- `list_targets` 为空或超时：提示用户重新打开目标小程序再重试一次；不要反复轮询。MCP 默认超时 30s（`~/.pi/agent/mcp.json` 的 `experimental.mcp_timeout`），服务未起时调 target/network 工具会白等一个超时，所以先确认服务再枚举。
- 出现多个可疑 target：先列出 title/url/type，让用户确认要分析 AppService 还是某个 WebView；不要随机切换。
- `save_script_source` 会写文件，或 `set_breakpoint_on_text` / `break_on_xhr` 会改变运行状态：先说明影响并获得用户确认；用户当前请求已经明确要求保存源码或动态断点时视为已确认，不重复追问。
- 停止脚本报错退出（非 0）但端口已空：说明进程树已停而 state 可能残留，再跑一次 `-Action Stop`（token 已丢失时任意合法 GUID 也会进入 stale 分支），它会在确认无监听者、无残留子进程后输出 `Removed stale WMPFDebugger state` 并返回 0；仍然不按端口杀进程。
- 任务结束、换 target、用户要求停止、代码已拿到 response、或最终报告已能完整复现请求链路时，执行“资源释放”流程。

## 输出要求

每次分析结束，优先给用户这些结果：

- 当前 target：AppService/WebView、target id、URL/title。
- 关键请求：method、URL、reqid、状态、响应摘要。
- 入口证据：initiator 调用栈、脚本 URL、行列号、关键函数/语句。
- 动态证据：断点处参数、局部变量、返回值或相关表达式求值。
- 收尾状态：是否已恢复 paused、是否已清理断点、是否保留或停止 WMPFDebugger 服务。
- 下一步：继续断点、保存源码、切换 target，或选择实现路线。
- 转交时：`handoff.json` 的 `task_id`/packet revision、primary owner 与 next stage、scope/budget/retention、`runtime_surface`、逐 ID validity、cookie scope 和 `success_predicate`。

## 后续路线选择

当需要在多个实现 skill 之间选择时，pi 环境没有 `question` 交互工具，直接给编号文本候选并等用户回答，不替用户默认选一个。默认候选：`trace`、`iv8-web-reverse`、`继续小程序断点分析`、`captcha-reverse`（小程序内验证码协议）。用户可以回答其他 skill 名称；转交前先确认该 skill 已安装或当前环境确实可用。该名称只用于当前转交，不在领域任务中永久改写本 Skill。

如果已经得到接口、签名、cookie/header、调用栈等可实现证据，先按用户最终交付目标筛选单调前进的候选，再列出候选、当前证据是否足够和每个候选的适用条件，等用户明确回复候选名或序号后再转交；不能把早期 browser/AST owner 当作 full-handoff 候选。

- `trace`：未知家族、多层链路，或恢复成 browser-free 的纯协议 Python 采集器；也包含 AST profile、env-patch profile 和 browser-hook profile 等聚焦阶段。适合已经能还原完整请求链路、目标是脱离微信运行。
- `captcha-reverse`：小程序内嵌验证码从 challenge 到 verify/check 的完整协议复现；本 skill 只交付 WMPF 内证据。
- `nv8-env-patch`：用户明确要求用 nv8 sandbox 执行已定位的小程序 JS 入口。
- `iv8-web-reverse`：用 Python + iv8 执行小程序/浏览器侧 JS，再用 requests 回放，适合想快速桥接已有 JS 生成 token/header。
- `自定义 skill 名称`：如果用户环境没有上述 skill，允许用户直接回复其他 skill 名称；收到后仅用于当前会话转交。只有用户另行提出维护/优化 Skill 的明确请求时，才进入 `skill-creator` 流程修改文件。

转交前如果当前微信小程序调试任务已经形成可复现链路，先执行“资源释放”流程。

## 更新记录

| 日期 | 要点 |
|---|---|
| 2026-08-31 (3) | 启动器 state 目录改为 `%LOCALAPPDATA%\pi\wechat-miniapp-reverse\`，互斥锁改为 `Local\Pi.WechatMiniappReverse.WmpfDebuggerService`（旧 OpenCode 命名已弃用；改名前必须先释放 lease）。修复 `Stop-ExactProcess`：PowerShell 5.1 下退出中进程的 `StartTime` getter 报错会得到 `$null`，直接链 `.ToUniversalTime()` 会抛“不能对 Null 值表达式调用方法”，造成进程树已杀但 lease/state 满盘残留；现改用 `Get-ProcessStartTicks` + `Test-ProcessExited` 判定，并在异常消息里带上脚本行号。 |
| 2026-08-31 (2) | 对齐 pi 运行时：工具调用改为 `mcp_call_tool(server="miniapp-reverse", ...)`，启停统一走 `scripts/wmpf-debugger-service.ps1`（git bash 转发 `.cmd` 会丢 `%~1` 并误报码 2），补齐退出码 0/1/2/3/4/5/6/7，新增“关键参数与默认值陷阱”（`exclude_minified` 默认会跳过压缩主包、`offset/length` 读压缩源码、`page_idx` 翻页、`max_scope_depth` 看深层闭包、`condition` 条件断点等）。 |
| 2026-08-31 | 接入本地逆向 skill 体系：按 `../_shared/js-reverse-workflow.md` 的 Routing Precedence / Stage / Handoff Envelope 统一跨 skill 名称与契约，下游改为 `trace`、`iv8-web-reverse`、`nv8-env-patch`、`captcha-reverse`，证据落盘改为 `js_reverse_cache/tasks/<task-id>/`。 |
| 2026-06-21 | 对齐 `miniapp-reverse` MCP 新能力：AppService 默认优先、Network ExtraInfo/loadingFailed、CDP 原始 POST body、Runtime console/exception/context、CPU Profiler、precise coverage、DOM event listener breakpoint、WebSocket handshake/frame error、断点/资源释放约束。 |

## 注意事项

- WMPFDebugger 调试服务必须在目标小程序启动前完成；如果用户操作顺序反了，建议重新启动 WMPFDebugger 服务并重新打开小程序。
- 看到 `you can now open any miniapps` 只代表调试服务已准备好，不代表 target 已接入；此时不要反复枚举 target，等待用户打开目标小程序。
- 默认 CDP endpoint 是 `devtools://devtools/bundled/inspector.html?ws=127.0.0.1:62000`。
- 当前 `miniapp-reverse` MCP 工具集不负责打开浏览器界面；默认只输出 DevTools URL 让用户手动打开，避免 UI 检测和 `about:blank` 往返浪费时间。
- `miniapp-reverse` MCP 不负责启动微信或选择具体小程序；用户需要手动打开目标小程序并触发行为。
- 如果用户最终目标变成“写一个脱离微信/浏览器的 Python 协议采集器”，将已有请求、脚本、调用栈证据按 `../_shared/js-reverse-workflow.md` 的 Handoff Envelope 转交给 `trace` 或 `iv8-web-reverse`。
