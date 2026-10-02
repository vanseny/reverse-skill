---
name: slider-captcha
description: |
  过滑块/拼图验证码（Aliyun Captcha V3 INPAINTING 抠物填洞型）的完整方法论：
  缺口检测（多信号投票 + 谷底提取）与真人轨迹拖拽（非线性标定 + CDP 可信输入）。
  触发关键词：滑块验证码、拼图验证码、滑动验证、过滑块、缺口检测、gap detection、
  阿里云验证码、Aliyun Captcha、INPAINTING、drag captcha、slider captcha、
  CaptchaVerifyParam、T001/T002、拖拽轨迹、CDP 拖拽。
  不适用：无痕验证（traceless / didk33e0 型，无滑块）—— 那是另一条路，见 [[captcha-solve]]。
---

# 过滑块验证码 (Slider / Puzzle Captcha)

## ACTION REQUIRED（读完后立刻执行）

1. `NOW`：确认验证码类型 —— 有滑块可拖才是本 skill；**无痕验证无滑块，直接转 `captcha-solve`**
2. `NOW`：读 `references/gap-detector.py`（规范实现，逐字可跑），不要凭记忆重写检测器
3. `NEXT`：确认前置条件（真浏览器 + CDP + 住宅出口），见「前置条件」，缺一不可
4. `ACT`：按「标准工作流」执行，不要停在分析

> **本 skill 的全部数字与结论来自实测**，出处 `zcode-api/tools/signup_drive.py`。
> 参考实现逐字抽取在 `references/gap-detector.py`。

---

## 零、先判类型（搞错类型是最高频的浪费）

| 类型 | 特征 | 走哪条路 |
|---|---|---|
| **滑块/拼图（本 skill）** | 有 `div.slider-move` 滑块 + 一张缺角背景图 + 一个拼图块 | 缺口检测 + 拖拽 |
| 无痕验证 traceless | 无滑块，SDK 静默算完给 token；`SceneId` 如 `didk33e0` | **转 `captcha-solve`**（内存 happy-dom 解） |

**判据**：页面 DOM 里有没有可拖的滑块元素。`didk33e0` 是 traceless scene，拿来当滑块做会**永远过不去**（无滑块可拖，token 被服务端拒）。

---

## 一、核心认知：为什么大多数做法必错

### 1.1 INPAINTING 让所有像素匹配类检测器失效

Aliyun V3 的拼图题是 **INPAINTING（抠物填洞）**：出题时把物件从背景里**抠掉并把洞修补平**，拼图块就是被抠走的那个物件。

⇒ **洞内像素 ≠ 碎片像素**。漏洞已经被 inpaint 填过，碎片原本的像素**在背景里已不存在**。

⇒ MSE / SAD / NCC / 模板匹配 / SSIM **全部必错**。用 TM_CCOEFF_NORMED 做过排序检验，碎片在背景里的最佳匹配位置是**结构性不存在**的。

⇒ 正确的信号是**纹理/高频细节的缺失**：洞是被抹平的区域，它的边缘密度、拉普拉斯响应、高频残差都低于周围。所有活下来的检测器都在量这个。

### 1.2 鼠标拖拽距离 ≠ 拼图块位移（非线性）

滑块 thumb 与鼠标**1:1 跟手**，但**拼图块不是**——它走一条缓动曲线。

老脚本假设 `dist = gap_x`（1:1），现象是"**三个检测器都算对了位置，但每次都判失败**"。实测标定（同一谜题内按住不放分 5 档量）：

| 拖拽 D | 拼图块位移 P | 比值 |
|---:|---:|---:|
| 40 | 8 | 0.200 |
| 80 | 28 | 0.350 |
| 120 | 60 | 0.500 |
| 160 | 103 | 0.644 |
| 200 | 157 | 0.785 |

二次拟合 `P = 0.003527·D² + 0.086071·D − 1.2`（5 点残差 ≤0.26px）。**必须反解出 D**，见 `references/gap-detector.py:drag_for_gap`。

> ⚠️ **该系数是逐站点标定的**。换站点/换 scene 必须重新标定（按住不放、分档测量、二次拟合），不要直接套用。

### 1.3 未过时题目会自动更换

松手后 SDK 约 **2s** 丢弃当前题、发新 `CertifyId`、换新拼图块。

⇒ **同一轮的检测结果不可跨轮复用**；每个候选都要**重新取图再检测**。
⇒ 内层候选循环实际只够试 ~2 个（2.1s 换题窗口限制），**重试主力是外层多轮**。

---

## 二、前置条件（缺一不可）

| 条件 | 要求 | 为什么 |
|---|---|---|
| **真浏览器 + CDP** | Chromium 系（Chrome/Cloak 等），开放 `--remote-debugging-port` | 必须发**可信**鼠标事件，见 §3.1 |
| **住宅出口** | 浏览器走住宅 sticky 代理，**不是**机房 IP | z.ai 对机房段敏感；`--proxy-bypass-list` 要把 CDN 域排除 |
| **CDN 直连** | `*.aliyuncs.com,*.alicdn.com,*.aliapp.org` 走直连不进代理 | 这些边缘节点在亚太，走美区住宅要 11–20s，直连 ~0.1s |
| **独立 profile/账号** | 并发时一账号一 profile 目录（Chrome 锁 profile 目录） | 否则第二个实例起不来 |

出口自检：进页面后 `fetch('https://api.ipify.org')` 确认落地 IP 是住宅段。

---

## 三、CDP 拖拽机制

### 3.1 为什么必须真输入

> **Aliyun Captcha V3 rejects untrusted (dispatchEvent) mouse events** —— 必须用真输入。
> Playwright 的 `mouse.*` 底层走 CDP Input dispatch，浏览器把那些事件标为 **trusted**。

⇒ **禁用** `element.dispatchEvent(new MouseEvent(...))`、`el.click()`、jQuery 触发。一律走 CDP/Playwright 的 `Input.dispatchMouseEvent`。

（例外：内存 happy-dom 求解器里用 synthetic `dispatchEvent` 是可以的——因为它跑在**自己的假 DOM** 里，不经过真浏览器的事件可信判定。那是 `captcha-solve` 的事。）

### 3.2 轨迹

两种可用形态，**都必须是多采样点连续移动**，单次瞬移（teleport）是**自动失败**：

- **真人轨迹重放**：从录制的真人拖动样本里切一段，按目标距离缩放 x、重定心 y。形状（含停顿）原样保留。样本文件如 `_captcha_plain.jsonl`（btoa 对 → zlib → `TrackList`）。
- **缓动合成**：quadratic ease-in-out，`steps = max(24, duration_ms/22)`（900ms → ~40 步），每步抖 `±1.1px x / ±0.6px y`，步间 sleep `0.008 + rand*0.012`。

```python
# 参考实现（references/gap-detector.py:human_drag）
page.mouse.move(start_x, y); time.sleep(0.06)
page.mouse.down();            time.sleep(0.05)
for i in 1..steps:
    eased = 2t² (t<0.5) else 1-(-2t+2)²/2
    page.mouse.move(start_x + eased*dist + jx, y + jy)
    time.sleep(0.008 + rand*0.012)
page.mouse.move(start_x + dist, y); time.sleep(0.15)
page.mouse.up()
```

**先清残留**：上一轮被强杀的进程可能留下未释放的 `mousePressed`，会污染点击。开拖前先补一个 `mouseReleased` 到 (0,0)。

### 3.3 DOM 定位（用页面自己的 class，不要猜）

| 目标 | 定位 | 判据 |
|---|---|---|
| 容器 | `.puzzle` | — |
| 背景图 | `.puzzle img` 中 `naturalWidth > 100` | 大的那张 |
| 拼图块 | `.puzzle img` 中 `naturalWidth <= 100` | 小的那张 |
| 当前块位置 | `img[piece].style.left`（如 `'182.5px'`） | 拖拽的起始参考 |
| 滑块把手 | `div.slider-move` / `#aliyunCaptcha-sliding-slider` | 中心**实时测量**，不要写死 |

若图片是 `static-captcha-*.aliyuncs.com` URL 而非 data-URI，**在页面上下文里 fetch 成 base64**（复用浏览器出口），不要在 Python 侧直接请求。

---

## 四、缺口检测

参考实现：`references/gap-detector.py`（`detect_gap` 全量）。

### 4.1 多信号投票（按实测命中率排序）

每个信号算一条 1-D 代价曲线，取低谷。**实测单槽 ≤5px 命中率**（n=117 未换题样本）：

| 信号 | 含义 | 命中率 |
|---|---|---:|
| **lap** | 拉普拉斯响应 `inside/around` | **47.9%** |
| **hf** | σ=0.4 高通残差 `inside/整列` | 39.3% |
| **lapc** | 拉普拉斯 `inside/整列` | 41.0% |
| **ring** | 梯度 `|dx|+|dy|` 的 `inside/around`（around=±8px 行） | 44.4% |
| **health** | 同 ring 分子，分母换**整列** | 39.3% |
| consensus | `|ring−health|≤15 ? mean : median(ring,health,lap)` | — |

**候选顺序（活）**：`lap, hf, lapc, ring, health, consensus` → `consensus±1..3` → **最后**才 `grad, mse, sad, ncc`。
兜底放最后，因为 §1.1：洞被 inpaint 过，像素匹配不成立。

### 4.2 峰值提取 = 谷底，不是 argmin

**`valley_pick`（平滑后"最宽显著低谷中心"）**取代了 argmin/容差聚类，**命中率翻倍**（同信号，仅改取峰方法：29.9%→47.0%，中位误差 46.6px→6.2px）。

参数（117 样本扫参得出）：Gaussian `σ=3.0`、`frac=0.20`、`minw=6`。

### 4.3 已废弃的写法（别重蹈）

| 写法 | 死因 |
|---|---|
| `_gapfind.py` ring-texture 对比 | 6 条判据全失败，被拉普拉斯族取代 |
| `_gapfind2.py` 窄带绝对平坦度 | 白边误报 |
| `_gapfind3.py` "ring 最可靠" | **前提被推翻**（ring 44.4% < lap 47.9%） |
| `cv-detect-gap.py` masked SAD+NCC 扫描 | 像素匹配族，原理性错误 |
| 纯 argmin / 模板匹配 | 见 §1.1 |

### 4.4 真值 / 误差

判"检测对不对"的真值 = **通过那一刻**抓的 `img[piece].style.left`。
⚠️ 不要用历史最大值——拖拽过冲会让它偏右。容差取 ±2px（拖拽本身就有 1–2px 误差）。

---

## 五、判定与重试

### 5.1 成功判据（**唯一可信**）

```
通过 = 响应体匹配 验证通过|验证成功
      OR 验证码容器数量 从 >0 变 0
```

⛔ **"面板关闭"单独出现不算通过**——失败时面板也会关约 2s（在换题）。把它当成功是最常见的假阳性。

服务端裁决形如 `{"VerifyCode":"T001","VerifyResult":true,"securityToken":"..."}`。

### 5.2 失败码

| 码 | 含义 | 处置 |
|---|---|---|
| `T001` / `VerifyResult:true` | 通过 | 收 |
| `F001` | 指纹不稳定（polyfill/补丁值被随机化） | 检查是否每轮随机了标志位 |
| `F008` | `certifyId` 重复/已被消费 | 每轮必须换新题重取 |
| `F005` | 请求过多（IP 被限） | 换出口 |
| `T002` 类 | 位置不对 | 下一轮 |

### 5.3 循环结构

- **内层**：单轮内候选列表。受 2.1s 换题窗口限制，**只够试 ~2 个**。
- **外层**：轮次。8 轮时整链通过率 **95.68% → 99.45%**（用 valley_pick 后）。
- 失败后**重新取图重新检测**，不要复用上一轮的答案（§1.3）。
- 并发：4 账号/组，组间串行；**每账号独立住宅出口**，否则同组共享 IP 触发账号级关联。

---

## 六、证据与产物

| 内容 | 建议落盘 |
|---|---|
| 每轮题目图 | `{tag}_r{N}_bg.png` + `_pz.png` |
| 标注样本 | `{certifyId}_bg.png` + `_pc.png` + `index.jsonl`（certifyId/answer/truth 来源） |
| 负样本（未过） | `_failed/{certifyId}_*.png` |
| 验证参数 | `_captcha_samples/{alias}_{ts}.json`（⚠️ 一次性，`Invoke duplicate!` 不可重放） |
| 真人轨迹库 | `_captcha_plain.jsonl` |

采集真值必须抓**通过那一刻**的 `style.left`（§4.4）。

---

## 七、路由上下文

**上游入口**: `../MASTER-ROUTING.md`、`../routing.md`
**相邻 skill**:
- 无痕验证（无滑块）→ `../captcha-solve/`
- 浏览器/CDP 操作基础 → `../browser-automation/`
- 页面 JS 分析（找 scene id、verify 端点） → `../js-reverse/`
- 反检测指纹对齐 → `../js-reverse-hello/`

**参考实现**: `references/gap-detector.py`（来自 `zcode-api/tools/signup_drive.py`）

---

## 任务完成自检（声称完成前 MUST 通过）

- [ ] 确认过是**滑块**题而非无痕题（有可拖滑块）
- [ ] 用真输入（CDP/Playwright），没有用 `dispatchEvent`/`click()`
- [ ] 拖拽距离经过**非线性反解**，不是 1:1
- [ ] 通过判据用了 `验证通过|验证成功` 或容器 >0→0，**没有**把"面板关闭"当通过
- [ ] 失败后**重新取图**，没有跨轮复用检测结果
- [ ] 每账号独立住宅出口
