---
name: captcha-solve
description: |
  阿里云验证码「求解器」——在内存 happy-dom 里补环境启动 Aliyun Captcha SDK，
  静默算出 captcha token（适用于无痕验证 traceless）。含令牌池/复用窗口/worker
  隔离/GC 治理/CPU 调速的完整工程化要点与踩坑清单。
  触发关键词：验证码求解器、captcha solver、无痕验证、traceless、Aliyun Captcha token、
  happy-dom 补环境、securityToken、certifyId、3007、F001、verifyParam、
  验证码池、captcha pool、内存泄漏 RSS、事件循环阻塞。
  不适用：有滑块的拼图验证码 —— 转 [[slider-captcha]]。
---

# 验证码求解器 (Aliyun Captcha — 内存求解)

## ACTION REQUIRED（读完后立刻执行）

1. `NOW`：确认是**无痕验证**（无滑块）。有滑块 → 立刻转 `../slider-captcha/`
2. `NOW`：定位权威实现（下节「权威实现」的表），**不要凭记忆重写求解器**
3. `NEXT`：逐条核对「工程化要点」——这些都是真人踩出来的，跳过会重现线上事故
4. `ACT`：按「接入方式」复制/接线，不要停在设计

> 本 skill 记录的是 `zcode-api` 里已经工程化到生产的一套求解器（Bun/TypeScript）。
> 它是**代码库内实现**而非独立可搬脚本，所以本 skill 给的是**架构 + 不变量 + 踩坑**，
> 以及每个事实的 `文件:行` 出处，便于在任何项目里复刻。

---

## 零、先判类型

| 类型 | 特征 | 走哪条路 |
|---|---|---|
| **无痕验证 traceless（本 skill）** | 无滑块，SDK 静默算完直接给 token | 内存 happy-dom 求解 |
| 滑块/拼图 INPAINTING | 有滑块要拖 | **转 `../slider-captcha/`** |

**判据**：页面有没有可拖的滑块元素。`didk33e0` 是 traceless scene；`36qgs6xb` 是 INPAINTING（滑块）scene。
把滑块题丢给内存求解器是**死路**（`probe-puzzle.ts:15` 的原话是"build solvePuzzle for real"，即当时判定为 dead end）。

---

## 一、权威实现（照这个读，别自创）

| 角色 | 文件 | 说明 |
|---|---|---|
| 对外唯一入口 | `src/proxy/captcha.ts:107` `getCaptchaToken(appVersion)` | 取配置 → 取令牌 |
| 背景预热 | `src/proxy/captcha.ts:125` `startCaptchaPool(appVersion)` | 启动时开池 |
| 令牌池 | `src/proxy/captcha-pool.ts:707` `takeCaptchaToken(cfg)` | 环形缓冲，sub-ms 取用 |
| 后端选择 | `src/proxy/captcha-solver.ts:18` `runCaptchaSolve(scene,region,prefix)` | 唯一后端 `"happy"` |
| **真求解器** | `src/proxy/captcha-happy.ts:2370` `solveTraceless({...})` | 2532 行，核心 |
| worker 调度 | `src/proxy/captcha-worker-dispatch.ts:342` `solveViaWorkerOrInProcess` | 有回退路径 |
| worker 入口 | `src/proxy/captcha-worker-entry.ts:15` | `node:worker_threads` |
| 令牌校验/错误码 | `src/proxy/captcha-token.ts`、`src/proxy/captcha-retry.ts` | 见 §五 |
| CPU 调速 | `src/proxy/captcha-cpu-governor.ts` | 见 §四.3 |

---

## 二、架构（数据流）

```
getCaptchaToken(appVersion)
  └─ fetchCaptchaConfig()            # 拉 verify 配置，见 §四.5 负缓存
  └─ takeCaptchaToken(cfg)           # 池
        ├─ 池非空 → 弹一个新鲜令牌（sub-ms），并触发 refill(urgent)
        └─ 池空   → solveRaced() 并行抢解（默认 3 个 racer）
              └─ solveViaWorkerOrInProcess()
                    ├─ worker 池热解（node:worker_threads，一次一个 solve）
                    │     entry: captcha-worker-entry.ts
                    │     从编译期文件资产载入: captcha-worker-asset.ts
                    └─ 回退：进程内解（worker 资产不可用时）
              └─ solveTraceless()
                    ├─ createDom()  → 预热 cookie(zcode.z.ai, 5min TTL)
                    ├─ happy-dom Window + polyfill/masking/guest-scope
                    ├─ initAliyunCaptcha({SceneId, mode:"popup",
                    │                    getInstance → startTracelessVerification})
                    └─ success 回调 → extractVerifyParam()
```

**网络层被完全替换**：happy-dom 拦截器接管所有请求；CDN 域（`\balicdn\.com`）从磁盘/内存缓存供给；**非 CDN 的同步 XHR** 必须丢进一个带 `SharedArrayBuffer + Atomics.wait` 的**阻塞 worker 线程**——因为 happy-dom 原生同步 XHR 会 spawn `process.argv[0] -e`，在编译后的 Bun 单文件二进制里必然崩。

---

## 三、接入方式

1. **拉源码**：从 `zcode-api` 取 `src/proxy/captcha*.ts`（10 个文件，见 §一表）。
2. **装依赖**：`happy-dom ^20.11.6`、`undici ^8.10.0`、`yaml ^2.5.0`；直接 import `happy-dom/lib/window/WindowBrowserContext.js`。
3. **构建 worker 包**：跑 `scripts/build-fork-worker.ts`（`bun build` 把 `captcha-worker-entry.ts` 打成 `captcha-worker-entry.bundle.js`）。该产物**是 gitignore 的构建产物**，每次 `bun build --compile` 前必须先跑。
4. **必须用 `with { type: "file" }`**（`captcha-worker-asset.ts:15`）：这是**唯一**能在 `bun build --compile` 单文件二进制里存活的 worker 机制（Bun 1.4 实测）。
5. **SDK 不打包**：AliyunCaptcha.js 在**运行时**从 `o.alicdn.com` 拉，缓存到 `~/.zcode-captcha-cdn-cache/<sha1(url)>`，内存 FIFO 上限 16。

---

## 四、工程化要点（每一条都是事故换来的）

### 4.1 worker 隔离 —— 否则冻死所有连接

> "Each solve runs inside a worker_threads Worker so the proxy's main event loop never blocks on the solver's Atomics.wait sync XHRs — in-process solving froze every connection during refill bursts (issue #54, PR #55)" — `captcha-worker-dispatch.ts:5-7`

深空闲后令牌池空，下一波请求并发起 8 个 solve × 6 重试，**每次冻结事件循环数十秒**，所有连接挂到重启。⇒ **每个 solve 必须独立 worker**；给硬超时（`CAPTCHA_SOLVE_TIMEOUT_MS` 默认 20s）到点 kill。

### 4.2 复用窗口与内存 —— RSS 只涨不跌的根因

> "the per-solve DOM/SDK-instance retention that drove the 2026-09-26 heap runaway (2.8 GB, every HTTP route wedged) lives in the WINDOW, not the module. We deliberately reuse the module and keep discarding the window." — `captcha-worker-dispatch.ts:40-42`
>
> "JSC only hands pages back to the OS on a FULL synchronous collection, so without this the serve process ratchets: every window generation's allocation peak becomes the permanent RSS floor (issue #50: 2.9 days -> 9.95GB resident)." — `captcha-happy.ts:2214-2218`

三条复合根因与对策：
1. 复用窗口内每次 solve 无条件重调 `initAliyunCaptcha` ⇒ 旧 SDK 实例图滞留。**对策**：`CAPTCHA_REUSE_MAX_SOLVES` **25→8**，世代峰值压到 ~1/3。
2. `_requestLog` 每窗口 fetch 都 push 从不截断（无界）。**对策**：截断。
3. `_memCdnCache` 按 pe 版本轮换只增不减。**对策**：淘汰。

外加 **节流强制 GC**：`destroyDom` 尾部 `Bun.gc(true)`，默认 5s 一次（`CAPTCHA_GC_MIN_INTERVAL_MS`）。

### 4.3 CPU 调速 —— Windows 上的静默失效

> "The previous fallback used os.loadavg(), which is hard-wired to [0,0,0] on Windows ... the governor read '0% busy' forever ... concurrency and the pool target climbed unchecked ... the runaway that pinned a core and grew the heap to 2.8GB until every HTTP route stopped answering (2026-09-26 field report)." — `captcha-cpu-governor.ts:48-54`

**对策**：用 `os.cpus()` 采样（无 `/proc/stat` 的主机也能用），**不要**用 `os.loadavg()`。迟滞 5%；`cpu>=limit` 时并发降 0（但 `readyTokens<poolSizeMin` 时保底 `max(1,..)`）。

### 4.4 指纹必须**稳定**，绝不能随机化

> "the happy-dom solver's polyfill/guest-patch values are deterministic and STABLE (never randomized) — Aliyun's risk engine correlates fingerprint stability across requests; randomizing per-solve flags it as `verifyCode: F001`." — `captcha.ts:11-14`

⚠️ 这是反直觉的：很多人以为"每次随机更像真人"，实际会被判 `F001`。**所有补丁值固定**。

### 4.5 出口 / CDN 路由

- 非 CDN 同步请求**不能**落回 happy-dom（会 spawn 崩掉，见 §二）。
- 同步 fetch worker 必须装 `ProxyAgent`，否则"sync XHR silently goes direct and times out on Aliyun CAPTCHA assets"（`captcha-happy.ts:48-53`）。
- cookie 缓存 5min；pe 包连续 2 次同 URL stall 就淘汰。
- **负缓存只缓"可用"配置**：HTTP 200 但字段为空也算失败（上游原版会把空配置缓存满 60s）；负 TTL 只 3s。
- 总预算用 `AbortSignal` 硬约束，且是**跨尝试共享**而非每次尝试各给一份。

### 4.6 超时绝不允许卡死

> "On the in-process fallback path a hung solve stalls the main event loop — fail fast and let the pool's retry ladder handle it" — `captcha-happy.ts:2374-2376`

**降级结果必须拒收**：长度 76 的垃圾 verifyParam "WILL 3007 upstream"（`captcha-happy.ts:2267-2276`）。

---

## 五、成功判据与错误码

### 5.1 令牌校验（`extractVerifyParam`, `captcha-happy.ts:2263-2293`）

- 长度必须 `< 200` 字符，否则**拒**（真令牌 ≈ **280** 字符）
- 必须是 base64-JSON，且 `securityToken` 长度 `>= 50`

### 5.2 错误码

| 码 | 含义 | 处置 |
|---|---|---|
| `3007` | 上游挑战（header 或 body `{"code":3007}`） | 重解一次 |
| `F001` | 指纹不稳定 | 查是否随机了补丁值（§4.4） |
| `F008` | `certifyId` 重复/已消费 | 池内去重，拒已发出的 certifyId |
| `F005` | 请求过多（IP 被限） | 触发 IP 重置；正则 `too many\|request was denied\|risk control\|...` |

池级：5 分钟内 `>=8` 失败且 3 分钟内 `0` 成功 → 触发 IP 重置，冷却 12min。

---

## 六、可调参数（关键项）

| 环境变量 | 默认 | 作用 |
|---|---|---|
| `CAPTCHA_POOL_MIN` / `_MAX` | 15 / max(min*4,60) | 池上下限 |
| `CAPTCHA_CACHE_TTL_MS` | 95000 | 令牌 TTL |
| `CAPTCHA_SOLVE_CONCURRENCY` | 3（`ZCODE_CAPTCHA_LOW_CPU=0` 时 8） | 并发道数 |
| `CAPTCHA_SOLVE_TIMEOUT_MS` | 20000 | 单次 solve 硬超时 |
| `CAPTCHA_WORKER_MAX_SOLVES` | 25 | worker 回收阈值 |
| `CAPTCHA_REUSE_MAX_SOLVES` | **8** | 复用窗口世代上限（§4.2） |
| `CAPTCHA_REUSE_MAX_IDLE_MS` | 120000 | 复用窗口空闲上限 |
| `CAPTCHA_GC_MIN_INTERVAL_MS` | 5000 | 强制 GC 最小间隔 |
| `CAPTCHA_CPU_LIMIT_PCT` | 100 | 宿主 CPU 上限（0=关调速） |
| `CAPTCHA_STALL_MS` | 6000 | 无 XHR 停顿判定 |
| `CAPTCHA_DEEP_IDLE_AFTER_MS` | 900000 | 零流量后停止造令牌 |

完整表见 `src/proxy/captcha-pool.ts:83-105` 与 `captcha-cpu-governor.ts:24-26`。

---

## 七、路由上下文

**上游入口**: `../MASTER-ROUTING.md`、`../routing.md`
**相邻 skill**:
- 有滑块的拼图验证码 → `../slider-captcha/`
- happy-dom 补环境 / 反检测基础 → `../js-reverse-hello/`
- 页面 JS 分析 → `../js-reverse/`
- 出口/代理编排 → `../browser-automation/`

---

## 任务完成自检（声称完成前 MUST 通过）

- [ ] 确认过是**无痕**题，不是滑块题
- [ ] solve 跑在**独立 worker** 里，主事件循环不阻塞
- [ ] 补丁/指纹值**固定不随机**（否则 F001）
- [ ] 复用窗口有世代上限 + 空闲上限 + 强制 GC（否则 RSS 单调涨）
- [ ] CPU 采样用 `os.cpus()` 而非 `os.loadavg()`（Windows）
- [ ] 令牌校验了长度 <200 且 securityToken>=50，垃圾结果被拒
- [ ] 超时硬约束，卡死即 fail-fast 交给池重试
