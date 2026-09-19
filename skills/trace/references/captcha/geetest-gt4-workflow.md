# Geetest GT4 Workflow

用于极验 GT4 滑块、文字点选、SVG 图标点选 `risk_type=svg_seed`、九宫格 `risk_type=nine`、消消乐 `risk_type=match`、五子棋 `risk_type=winlinze` 和无感 `risk_type=ai` 的 `/load -> pow/biht/w -> /verify` 纯协议复现，以及客户端 bundle 更新后从连续 `forbidden` 中恢复。

## 识别信号

- `/load` 返回 `lot_number`、`pow_detail`、`payload`、`process_token`、`payload_protocol`、`pt`；滑块还有 `bg`、`slice`，文字点选是 `captcha_type=word` + `imgs` + `ques`，SVG 图标点选是 `captcha_type=svg_seed` + `question_path` SVG + `answer_path` PNG base64，九宫格是 `captcha_type=nine` + `imgs` + `ques` + `nine_nums`，消消乐是 `captcha_type=match` + `imgs` + 3x3 数字矩阵 `ques`，五子棋是 `captcha_type=winlinze` + `imgs` + 5x5 数字矩阵 `ques`，无感是一键通过页面里的 `risk_type=ai` / `captcha_type=ai`。
- `/verify` 使用同轮 `lot_number/payload/process_token` 和动态 `w`。
- 滑块 `wPayload` 常见字段：`setLeft`、`passtime`、`userresponse`、`pow_msg`、`pow_sign`、`gee_guard`、`em` 和 bundle 动态字段。
- 文字点选 `wPayload` 无 `setLeft`；`userresponse` 是整数坐标对，见下文“文字点选（word）”。
- 九宫格 `wPayload` 无 `setLeft`；`userresponse` 是 1 基 `[row,col]` 对，见下文“九宫格（nine）”。
- SVG 图标点选 `wPayload` 无 `setLeft`；`userresponse` 是当前可见帧内的 1 基 `[row,col]`，目标帧由 `passtime` 对齐 SVG keyframes 表达，见下文“SVG 图标点选（svg_seed）”。
- 消消乐 `wPayload` 无 `setLeft`；`userresponse` 是两格相邻交换坐标 `[[x,y],[x,y]]`，见下文“消消乐（match）”。
- 五子棋 `wPayload` 无 `setLeft`；`userresponse` 是移动棋子的源格和目标空格，见下文“五子棋（winlinze）”。
- 无感 `wPayload` 无 `setLeft/passtime/userresponse`，只提交设备空值、PoW、GCT `biht`、`gee_guard`、`em` 和 bundle 动态字段，见下文“无感（ai）”。

## 标准流程

1. 请求 `/load`，保存完整 JSONP 响应、Cookie 和图片地址。
2. 下载 `slice/bg`，校验真实图片后用 `ddddocr.slide_match(..., simple_target=True)` 得到原图缺口 `gap_x`，不要直接把它当成 `setLeft`。
3. 按 `pow_detail` 生成 `pow_msg/pow_sign`；当前格式是 `version|bits|hashfunc|datetime|captcha_id|lot_number||nonce`，其中 `lot_number` 和 `pow_detail` 必须来自本轮 `/load`。
4. 把原图坐标映射为页面提交坐标，再计算 `userresponse`。当前 300px 背景图验证公式为 `scale = 0.8876 * min(bg_width, 340) / bg_width`、`setLeft = round((gap_x - 2) * scale)`、`userresponse = setLeft / scale + 2`。
5. 从本轮 `gct_path` 原始源码计算 `biht`，并生成 `gee_guard`、`em`；不要把格式化后的 GCT 当作原始输入。
6. 组装当前 bundle 要求的 `wPayload`。
7. 对 `pt=1`，常见 `w` 是 `AES-CBC-PKCS7(compact_json, random16, iv='0000000000000000') + RSA-PKCS1-v1_5(random16)` 的 hex 拼接。这里的 `random16` 是 16 字节 ASCII hex 字符串，例如 `secrets.token_hex(8)`。
8. 用同轮外层参数请求 `/verify`，仅当 `status == "success"` 且 `data.result == "success"` 时算通过。

## 有 Bundle 时的快速路径

用户同时给出当前 `gcaptcha4.js`/`1.js` 和请求样本时，优先走下面的浏览器无关路径。已经有源码时不要先启动浏览器、做全量 AST 解混淆或手写 AES/RSA：

1. 先尝试最小首轮 `/load`：只传动态 JSONP `callback`、`captcha_id`、`client_type=web`、目标 `risk_type`、`pt=1`、`lang`。很多公开 GT4 配置不要求预先提供 `lot_number/payload/process_token`；`lang=zh` 与 `lang=zho` 必须对齐浏览器实抓。
2. 如果样本中的 `/load` 请求已经带 `lot_number/payload/process_token`，先区分请求输入和响应输出。后续 `/verify` 应使用 `/load` 响应返回的新值；两阶段 token 不同通常是正常刷新，不是断轮。
3. 离线暴露 webpack require，只执行 PoW 和 `w` 模块；同时从源码运行时读取 `_lib`、`lib._abo`。不要执行入口 UI 模块。
4. 按目标类型生成答案字段：滑块下载同轮图片并映射 `setLeft/userresponse`；文字点选识别提示字和背景坐标；SVG 图标点选离线渲染 3 帧 27 个 SVG 候选并输出 `frame/userresponse/passtime`；九宫格识别 0 基小格索引并转 1 基 `[row,col]`；消消乐只解析 `ques` 的相邻交换坐标；五子棋枚举非空棋子移动到空格后的五连线。
5. 下载并原样执行本轮 GCT，读取其写入的 `biht`。当前 GCT 写入的是十进制字符串，不要强制转成整数。
6. 组装 `wPayload`，调用 bundle 的 `w` 模块，真实等待 `passtime` 后提交同轮 `/verify`。
7. 连续创建三轮新 challenge 验证，不能在同一个失败 lot 上扫描大量坐标。

可直接复用：

- `scripts/gt4_bundle_helper.js`：读取当前 bundle，动态提取元数据、PoW、GCT 和 `w`。
- `scripts/gt4_replay.py`：同轮 `/load -> 图片 -> helper -> sleep -> /verify` 模板。
- `scripts/gt4_pure_replay.py`：不执行 JavaScript 的纯 Python `/load -> OCR -> PoW/GCT/AES/RSA -> sleep -> /verify` 模板。
- `scripts/gt4_ai_pure.py`：不执行 JavaScript 的纯 Python `risk_type=ai` 无感 `/load -> PoW/GCT/AES/RSA -> /verify` 模板。
- `scripts/gt4_winlinze_replay.py` + `scripts/gt4_winlinze_helper.js`：官方 Demo 五子棋 `risk_type=winlinze` 的 `/load -> 解棋盘 -> bundle 生成 w -> /verify` 模板。

运行模板：

```bash
python scripts/gt4_replay.py \
  --captcha-id <captcha_id> \
  --bundle <当前 gcaptcha4.js> \
  --helper scripts/gt4_bundle_helper.js
```

## SVG 图标点选（svg_seed）

用于官方 Demo 或业务站分配到 `risk_type=svg_seed` 时的协议复现。该分支看起来像 3 轮图标切换，但实际是同一个 `question_path` SVG 通过 CSS keyframes 在 3 帧之间循环；每个 challenge 只提交一次。

### 识别信号

- `/load` URL 含 `risk_type=svg_seed`，响应 `data.captcha_type == "svg_seed"`。
- 响应含 `question_path`：`300x260` SVG，内部有 3 个 `geetest_frame_1/2/3` 分组，每帧 3x3 共 9 个候选。
- 响应含 `answer_path`：目标图标 PNG base64，通常为 `48x48`。
- 响应含 SVG `<style>`，定义每帧 `@keyframes geetest_frame{n}_animation_*` 和总周期，如 `animation:... 7.196s infinite steps(1)`。

### 离线识别

1. 固定同轮 `/load` 响应，保存完整 JSONP、Cookie、`question_path`、`answer_path`、`pow_detail/gct_path/payload/process_token`。
2. 从 `question_path` 中提取 `<defs>`，再遍历 3 个 frame 分组下的候选 `<g transform="translate(x,y)...">`。
3. 对每个候选构造独立 `48x48` SVG：`viewBox = x-24, y-24, 48, 48`，保留原始 `<defs>` 和候选 `<g>`。
4. 将 27 个候选 SVG 和 `answer_path` PNG 都渲染成 `48x48 RGBA`。在 Node 环境优先 `sharp`；没有 `sharp` 时可用浏览器 canvas 取证，但最终交付要回到离线渲染或明确依赖。
5. 按 `sad = |RGB| + 2*|alpha|` 排序，可同时保留 `mse` 和 alpha IoU。输出最佳候选的 `frame`、`row`、`col`、`userresponse=[row,col]`。

### 帧与 passtime

`svg_seed` 的 `wPayload` 没有独立 `frame` 字段。服务端通过 `passtime` 判断提交时应该处于哪一帧，因此 `passtime % animationDuration` 必须落在目标 frame 的可见区间。

从 SVG style 中解析目标帧可见区间：

```text
@keyframes geetest_frame2_animation_hash {
  35.10% { opacity:1 }
  70.65% { opacity:1 }
}
.geetest_frame_2_hash.geetest_frame_active_hash {
  animation: geetest_frame2_animation_hash 7.196s infinite steps(1)
}
```

计算：

```python
start_ms = round(duration_ms * start_percent / 100)
end_ms = round(duration_ms * end_percent / 100)
passtime = start_ms + 120  # 建议先用 100-200ms guard，确认多轮成功后再压
```

时间压缩经验：

- 默认不要再取帧中点；优先取 `start_ms + 120ms`。
- 真实等待用 remaining 模式：从 `/load` 发起后开始计时，离线识别、PoW 和 `w` 生成耗时可抵扣，最终只 sleep `max(0, passtime - elapsed_ms)`。
- 为降低等待，可优先接受 frame 1/2；遇到 frame 3 可以重新 `/load`。若强制只接受 frame 1，可能多刷几次 challenge，但成功样本中 `passtime=121ms` 且实际 sleep 为 0。

### wPayload

当前 bundle 下字段集合示例：

```python
w_payload = {
    "passtime": passtime,
    "userresponse": [row, col],  # 1 基坐标，只表示当前目标帧内格子
    "device_id": "",
    "lot_number": lot_number,
    "pow_msg": pow_msg,
    "pow_sign": pow_sign,
    "geetest": "captcha",
    "lang": "zh",
    "ep": "123",
    "biht": biht,
    "gee_guard": {"roe": {"aup": "3", "sep": "3", "egp": "3", "auh": "3", "rew": "3", "snh": "3", "res": "3", "cdc": "3"}},
    **fixed_fields,
    **lot_fields,
    "em": {"ph": 0, "cp": 0, "ek": "11", "wd": 1, "nt": 0, "si": 0, "sc": 0},
}
```

2026-07 官方 Demo bundle 实抓：`fixed_fields={"YYhg":"BjI0"}`，`lot_rules={"n[1:4]":"n[24:27]"}`，例如 lot 生成字段 `{"2082":"d4ee"}`。这些字段必须从当前 raw bundle 解析，不要长期硬编码。

`w` 加密仍是 GT4 通用壳：`AES-CBC-PKCS7(compact_json, random16_ascii_hex, iv='0000000000000000') + RSA-PKCS1_v1_5(random16_ascii_hex)`。

### 标准回放

1. `GET /load`：`callback`、`captcha_id`、`client_type=web`、`risk_type=svg_seed`、`lang=zh`。
2. 离线识别 SVG，得到 `frame` 和 `[row,col]`。
3. 解析 SVG keyframes，为目标 `frame` 生成压缩后的 `passtime`。
4. 计算 PoW、下载 raw `gct_path` 计算 `biht`，从 raw `gcaptcha4.js` 解析 `fixed_fields/lot_rules`。
5. 组装 `wPayload` 并纯 Python 生成 `w`。
6. 从 `/load` 开始计时，sleep 剩余时间后请求 `/verify`。仅当 `status == "success"`、`data.result == "success"`、`fail_count == 0` 算通过。

### svg_seed 高频排查

1. 把 `svg_seed` 当普通九宫格：九宫格没有 SVG keyframes；`svg_seed` 的 frame 由 `passtime` 表达。
2. 只提交正确 `[row,col]`，但 `passtime` 不在目标帧区间：服务端会失败。真实案例中第 3 帧 `[2,2]` 配 `passtime=1800` 失败，因为 1800ms 落在早帧。
3. 只等目标帧但不冻结或不抵扣时间：浏览器自动化点击期间可能动画切帧；纯协议也可能声明时间与实际等待不一致。
4. 在浏览器内 `dispatchEvent`：能触发 `/verify`，但非可信事件常失败。浏览器取证必须用 CDP/Playwright 真实点击或只用于离线识别。
5. 直接点击 SVG 内 `<g>`：页面透明 click layer 会拦截；若做浏览器自动化，要把代理元素挂到验证码窗口内部并冻结目标帧。
6. 用格式化后的 GCT 计算 `biht` 或写死 bundle 动态字段：必须用同轮 raw GCT 和当前 raw bundle。

### 已验证案例结论

- 浏览器暂停帧确认：进入通用 `w` 之前的 `wPayload` 除 PoW 随机项外可由离线 helper 完全复现，`w.length == 1408`。
- 全 browser-free 流程已通过：`/load -> sharp 离线识别 -> frame passtime -> pure Python w -> /verify`，连续 fresh challenge 返回 `result:"success"`。
- 时间压缩已通过：frame 2 样本 `passtime=2135ms`、实际 `sleep_ms=1562ms` 成功；frame 1 样本 `passtime=121ms`、实际 `sleep_ms=0` 成功。

## 普通图标点选（icon）

用于官方 Demo 或业务站分配到 `risk_type=icon` / `captcha_type=icon` 时的纯协议复现。该分支看起来像 SVG 图标点选，但实际上是普通背景图 `imgs` 加三个提示图标 `ques[]`；答案是背景图中三个图标中心点，不是 3x3 格子。

### 识别信号

- `/load` URL 含 `risk_type=icon`，响应 `data.captcha_type == "icon"`。
- 响应含 `imgs`（背景图）和 `ques[]`（三个提示图标 PNG，顺序就是点击顺序）。
- 没有滑块 `bg/slice/setLeft`，也没有 `svg_seed` 的 `question_path/answer_path/keyframes`。

### 标准流程

1. `GET /load`：保存同轮 JSONP、Cookie、`lot_number/payload/process_token/payload_protocol/pt/pow_detail/gct_path/imgs/ques`。
2. 下载当前 raw `gcaptcha4.js` 和 raw GCT。bundle 元数据、`fixed_fields`、`lot_rules`、`biht` 必须来自当前文件；格式化源码只用于阅读。
3. 下载背景图和三个 `ques_*.png`。识别器只负责输出三个背景图原始像素中心点，顺序必须对应 `ques_0/1/2`。
4. 坐标编码与 word 相同，都是 0 到 10000 的比例整数，且没有 per-click 时间戳：

```python
userresponse = [
    [round(x / width * 10000), round(y / height * 10000)]
    for x, y in centers  # 背景图像素中心，按 ques 顺序
]
```

5. 组装 `wPayload`：`passtime`、`userresponse`、`device_id:""`、`lot_number`、`pow_msg/pow_sign`、`geetest:"captcha"`、`lang`、`ep`、`biht`、`gee_guard`、bundle `fixed_fields/lot_fields` 和 `em`。
6. `w` 加密与其他 GT4 分支相同：`AES-CBC-PKCS7(compact_json, random16_ascii_hex, iv=0*16) + RSA-PKCS1_v1_5(random16_ascii_hex)` 的 hex 拼接。
7. `GET /verify` 使用同轮 `/load` 返回的外层参数。控制台或报告必须保存真实 `/verify` 原始 JSONP；只看本地 assignment 分数不算通过。

### icon 高频排查

1. 把 `icon` 当 `svg_seed`：`icon` 没有帧、没有 1 基 `[row,col]`，也不靠 `passtime` 表达 frame。
2. 把 `userresponse` 写成像素坐标、0-1 比例、小格坐标或带时间戳三元组：服务端期望 `round(ratio*10000)` 的整数对。
3. 只用 ddddocr 或通用 OCR 做图标匹配：官方 Demo icon 实测 ddddocr 基线很弱，协议壳验证后应把识别训练交给 `captcha-vision`。
4. 只训练检测框不训练排序：图标题难点常在 `ques_0/1/2` 与背景候选的一对一排序；需要 pair ranker 或 assignment ranker，并用服务端 `/verify` hard negatives 验收。
5. 为了提速直接切 ONNX：ONNX 坐标可能接近，但类别分数分布可能偏离 Ultralytics PT 路径；必须同图 parity + fresh `/verify` 通过率验证后再作为默认。
6. 在同一个失败 lot 上无限扫坐标：GT4 会累积 `fail_count`；批量验收要用 fresh challenge，正常 3 次失败后换题或进入明确的 oracle mining 流程。

## 九宫格（nine）

用于官方 Demo 或业务站分配到 `risk_type=nine` 时的纯协议复现。该分支和滑块/文字点选共用 PoW、GCT `biht`、bundle 动态字段、AES/RSA `w` 壳，但答案字段完全不同。

### 识别信号

- `/load` URL 含 `risk_type=nine`，响应 `data.captcha_type == "nine"`。
- 响应含 `imgs`（整张 3x3 九宫格图）、`ques[]`（目标提示图，常为透明 PNG）、`nine_nums`（通常为 3）。
- 没有滑块 `bg/slice/setLeft`，也不是 word 的 `round(x/w*10000)` 坐标。

### 标准流程

1. `GET /load`：`callback`、`captcha_id`、`client_type=web`、`risk_type=nine`、`lang=zh`。保存 JSONP、Cookie、`lot_number/payload/process_token/payload_protocol/pt/pow_detail/gct_path/imgs/ques/nine_nums`。
2. 下载同轮 `gcaptcha4.js`、raw `gct_path`、`imgs` 和所有 `ques[]`。提示图若有透明通道，先合成白底用于识别；九宫格按 `nine_nums` 等分裁出 `tile_0.jpg` 到 `tile_8.jpg`，索引规则为从左到右、从上到下的 0 基顺序。
3. 图片识别只输出三个 0 基索引，例如 `[0,3,8]`。识别模型训练、GPU 依赖、CLIP/YOLO 混合策略和批量压测属于独立 skill `captcha-vision`，不要把训练流程塞进本协议 skill。
4. 把 0 基索引转成浏览器明文 `userresponse`：

```python
def indices_to_userresponse(indices, count=3):
    return [[index // count + 1, index % count + 1] for index in indices]
```

示例：`[0, 3, 8] -> [[1,1],[2,1],[3,3]]`。顺序使用识别器输出顺序即可；同类三图通常服务端不强依赖点击顺序，但不要把索引写成 `[x,y]` 或 0 基坐标。

5. 组装 `wPayload`，字段集合与 word/match 类似但答案为九宫格坐标：

```python
w_payload = {
    "passtime": passtime,
    "userresponse": indices_to_userresponse(indices, nine_nums),
    "device_id": "",
    "lot_number": lot_number,
    "pow_msg": pow_msg,
    "pow_sign": pow_sign,
    "geetest": "captcha",
    "lang": "zh",
    "ep": "123",
    "biht": biht,
    "gee_guard": gee_guard,
    **fixed_fields,
    **lot_fields,
    "em": em,
}
```

6. `w` 加密仍是 `AES-CBC-PKCS7(compact_json, random16_ascii_hex, iv=0*16) + RSA-PKCS1_v1_5(random16_ascii_hex)` 的 hex 拼接。
7. `GET /verify` 使用同轮 `/load` 返回的 `lot_number/payload/process_token/payload_protocol/pt`，`risk_type` 用 `data.captcha_type` 或固定 `nine`。仅当 `status == "success"`、`data.result == "success"`、`fail_count == 0` 算通过。

### nine 高频排查

1. 把 0 基索引直接作为 `userresponse`：服务端期望 1 基 `[row,col]` 对。
2. 把坐标写成图片像素、百分比、word 的 `round(ratio*10000)` 或滑块距离：nine 只提交九宫格行列。
3. 混用不同轮 `imgs/ques/lot_number/payload/process_token/cookies/gct_path`：识别结果正确也会失败。
4. 用格式化后的 GCT 算 `biht` 或把 bundle 固定字段写死：nine 与其他 GT4 分支一样依赖 raw GCT 和当前 bundle 元数据。
5. 只看本地识别是否“像对了”：必须用 fresh challenge 的 `/verify` 响应判定，至少连续多轮，不能把一轮成功当稳定。
6. `passtime=0` 在官方 Demo 曾可通过，但必须先修改代码让 `0` 不被 `or random` 吞掉，并用多轮 fresh 验收；业务站可能存在独立时序/风控门，不能跨站硬套。

## 消消乐（match）

用于官方 Demo 或业务站分配到 `risk_type=match` 时的纯协议复现。加密壳与滑块/文字点选共用，但答案字段完全不同。

### 识别信号

- `/load` URL 含 `risk_type=match`，响应 `data.captcha_type == "match"`。
- 响应含 `imgs`（通常是 emoji 小图数组）和 `ques`（3x3 数字矩阵）。数字代表图片类型，不需要 OCR。
- 没有滑块 `bg/slice`，不要套 `setLeft`；也不是文字点选的图片像素比例坐标。

### 标准流程

1. `GET /load`：`callback`、`captcha_id`、`challenge`、`client_type=web`、`risk_type=match`、`lang`。2026-07-26 官方 Demo 实抓为 `lang=zh`，旧教程可能写 `zho`，以当前浏览器请求为准。
2. 保存同轮 `lot_number/payload/process_token/payload_protocol/pt/pow_detail/gct_path/ques` 和 `captcha_v4_user`。
3. 解 `ques`：枚举相邻两格交换，交换后任意一行或一列三格相同即为答案。坐标必须按前端 `dataId`，也就是 `ques[x][y]` 的两个索引；第一维对应前端 `left`/列，第二维对应 `top`/行。

```python
def solve_match_puzzle(ques):
    grid = [list(row) for row in ques]
    width = len(grid)
    height = len(grid[0]) if grid else 0

    def has_clear_line(candidate):
        for x in range(width):
            if len(set(candidate[x])) == 1:
                return True
        for y in range(height):
            if len({candidate[x][y] for x in range(width)}) == 1:
                return True
        return False

    for x in range(width):
        for y in range(height):
            for dx, dy in ((1, 0), (0, 1)):
                nx, ny = x + dx, y + dy
                if nx >= width or ny >= height or grid[x][y] == grid[nx][ny]:
                    continue
                candidate = [row[:] for row in grid]
                candidate[x][y], candidate[nx][ny] = candidate[nx][ny], candidate[x][y]
                if has_clear_line(candidate):
                    return [[x, y], [nx, ny]]
    raise ValueError(f"no valid adjacent swap: {ques!r}")
```

4. 组装 `wPayload`，字段顺序与浏览器一致：

```python
w_payload = {
    "passtime": passtime,
    "userresponse": userresponse,  # [[x,y],[x,y]]，直接对应 ques[x][y]
    "device_id": "",
    "lot_number": lot_number,
    "pow_msg": pow_msg,
    "pow_sign": pow_sign,
    "geetest": "captcha",
    "lang": "zh",
    "ep": "123",
    "biht": biht,
    "gee_guard": gee_guard,
    **fixed_fields,
    **lot_fields,
    "em": em,
}
```

5. `w` 加密与其他 GT4 分支相同：`AES-CBC-PKCS7(compact_json, random16_ascii_hex, iv=0*16) + RSA-PKCS1_v1_5(random16_ascii_hex)`。
6. 真实 `sleep(passtime/1000)` 后请求 `/verify`，参数必须使用同轮 `/load` 输出，并且 `risk_type` 使用 `data.captcha_type` 或固定 `match`，不要沿用教程里误写的 `slide`。
7. 仅当 `status == "success"` 且 `data.result == "success"` 且 `fail_count == 0` 算通过。

### match 高频排查

1. 用格式化后的 `gcaptcha4.js` 解析顶部 XOR 字符串表：会找不到 `decodeURI(...)` 或解析错动态字段；纯 Python 路径必须保存 raw bundle，格式化版只用于阅读。
2. 用格式化/beautify 后的 GCT 计算 `biht`：`Function.prototype.toString()` 原文变了，结果不可信；必须用同轮 raw `gct_path`。
3. 把 `verify.risk_type` 写成 `slide`：服务端会按错误类型校验，可能稳定失败。
4. 把 `userresponse` 写成图片坐标、百分比坐标、滑块距离或文字点选的 `round(ratio*10000)`：match 正确值是 `[[x,y],[x,y]]` 的相邻交换格子。
5. 沿用旧文章固定动态字段：2026-07-26 官方 Demo 当前为 `fixedFields={"YYhg":"BjI0"}`、`lotRules={"n[1:4]":"n[24:27]"}`，但仍必须从当前 bundle 解析，不可长期硬编码。
6. 只看 `w` 长度：当前成功样本常见 `w_length=1440`，长度会随 JSON 变化，不能当作正确性判据。
7. 对同一个失败 lot 反复扫坐标：应重新 `/load` fresh challenge，保持同轮 token 和真实时序。

## 五子棋（winlinze）

用于官方 Demo 或业务站分配到 `risk_type=winlinze` 时的协议复现。该分支和 `match/word/nine` 共用 PoW、GCT `biht`、bundle 动态字段、AES/RSA `w` 壳，但答案字段是“移动一个棋子到空格”。

### 识别信号

- `/load` URL 含 `risk_type=winlinze`，响应 `data.captcha_type == "winlinze"`。
- 响应含 `imgs`（棋子图片数组）和 `ques`（通常为 5x5 数字矩阵）。`0` 是空格，非零数字是棋子类型。
- 没有滑块 `bg/slice/setLeft`，也不是 `match` 的相邻交换、`nine` 的 1 基九宫格坐标或 `word` 的图片比例坐标。

### 标准流程

1. `GET /load`：`callback`、`captcha_id`、`challenge`、`client_type=web`、`risk_type=winlinze`、`lang=zh`。保存同轮 `lot_number/payload/process_token/payload_protocol/pt/pow_detail/gct_path/ques` 和 `captcha_v4_user`。
2. 解 `ques`：枚举一个非空棋子移动到一个空格，移动后任意一行、一列或两条对角线出现同色 5 连即为答案。
3. `userresponse` 是 0 基 `[row,col]` 坐标对，顺序是先非空棋子、再目标空格：

```python
def solve_winlinze(ques):
    grid = [list(row) for row in ques]
    size = len(grid)

    def lines():
        for row in range(size):
            yield [(row, col) for col in range(size)]
        for col in range(size):
            yield [(row, col) for row in range(size)]
        yield [(i, i) for i in range(size)]
        yield [(i, size - 1 - i) for i in range(size)]

    def has_win(candidate):
        for line in lines():
            values = [candidate[row][col] for row, col in line]
            if values[0] != 0 and all(value == values[0] for value in values):
                return True
        return False

    empties = [(r, c) for r in range(size) for c in range(size) if grid[r][c] == 0]
    pieces = [(r, c) for r in range(size) for c in range(size) if grid[r][c] != 0]
    for dst in empties:
        for src in pieces:
            candidate = [row[:] for row in grid]
            candidate[dst[0]][dst[1]] = candidate[src[0]][src[1]]
            candidate[src[0]][src[1]] = 0
            if has_win(candidate):
                return [list(src), list(dst)]
    raise ValueError("no one-move win")
```

4. 组装 `wPayload`，字段集合与 `match/word/nine` 类似但答案为五子棋移动坐标：

```python
w_payload = {
    "passtime": passtime,
    "userresponse": userresponse,  # [[source_row,source_col],[empty_row,empty_col]]
    "device_id": "",
    "lot_number": lot_number,
    "pow_msg": pow_msg,
    "pow_sign": pow_sign,
    "geetest": "captcha",
    "lang": "zh",
    "ep": "123",
    "biht": biht,
    "gee_guard": gee_guard,
    **fixed_fields,
    **lot_fields,
    "em": em,
}
```

5. `w` 加密仍由当前 bundle 决定；已验证模板用 `gt4_winlinze_helper.js` 暴露 webpack require，调用 PoW 模块和 `req(31).default(compact, {options:{pt:'1'}})` 生成 `w`。
6. `GET /verify` 使用同轮 `/load` 输出，`risk_type` 使用 `data.captcha_type` 或固定 `winlinze`。仅当 `status == "success"`、`data.result == "success"`、`fail_count == 0` 算通过。

### 可直接复用

```bash
python scripts/gt4_winlinze_replay.py \
  --captcha-id <captcha_id> \
  --bundle <当前 raw gcaptcha4.js> \
  --helper scripts/gt4_winlinze_helper.js \
  --captcha-user <captcha_v4_user> \
  --passtime 0
```

若已有浏览器导出的 `/load` 样本，只验证解题和 `w` 生成：

```bash
python scripts/gt4_winlinze_replay.py \
  --from-capture js_reverse_cache/req_load_winlinze.json \
  --bundle js_reverse_cache/gcaptcha4.raw.js \
  --helper scripts/gt4_winlinze_helper.js \
  --gct js_reverse_cache/gct4.raw.js \
  --dry-run
```

### winlinze 高频排查

1. 把坐标顺序写反：浏览器点击流程是先选非空棋子，再选目标空格，明文为 `[[source_row,source_col],[empty_row,empty_col]]`。
2. 把 `row/col` 当成前端 CSS 的 `left/top`：提交的是 0 基矩阵坐标，不是像素坐标。
3. 套 `match` 解法：`match` 是两格相邻交换；`winlinze` 是把一个棋子移动到任意空格，源格会变空。
4. 套 `nine` 解法：`nine` 是 1 基 `[row,col]`；`winlinze` 是 0 基 `[row,col]`。
5. 用格式化后的 GCT 参与 `biht`：仍必须使用本轮 raw `gct_path`。
6. 只看 `w` 长度：当前样本常见 `w_length=1440`，长度只能作版本证据，不能当正确性判据。
7. 官方 Demo 当前实测 `passtime=0` 可过；业务站可能另有时序门，应从低值逐级压缩并以 `/verify` 为准。

## 纯 Python 极速路径

用户明确要求“纯 Python / 纯算”且已提供当前 bundle 时，按下面顺序执行，避免先做一轮 Node/vm 再返工：

1. 先在工作区搜索 `gt4_pure.py`、`gt4_protocol.py`、`RSA_N_HEX`、`PKCS1_v1_5`。已有实现只作为算法和公钥来源，必须用当前 bundle 与新 challenge 重新验证。
2. 直接复制或改造 `scripts/gt4_pure_replay.py`，依赖仅为 `requests`、`ddddocr`、`Pillow`、`pycryptodome`。运行路径不得导入 `subprocess`，不得调用 Node、iv8、ExecJS、jsdom 或浏览器。
3. 用完整 bundle 文本解出顶部 XOR 字符串表，再解析 `_lib/lib._abo` 初始化段。大字符串表可能占据源码前数十万字符，不要用 `source[:20000]` 查元数据；先定位明文 `n[...]` lot rule，再向前截取小窗口查 `_lib` 对象。
4. Python 的 `decodeURI` 兼容实现必须保留 URI reserved 字符的 `%XX` 形式；不能无条件使用 `urllib.parse.unquote()`，否则 XOR 输入长度可能变化，导致后半段字符串表错位。
5. PoW 明文固定核对为 `version|bits|hashfunc|datetime|captcha_id|lot_number||nonce`。当前 bundle 调 PoW 模块的最后一个参数是空字符串，不能误传 `/load` 返回的长 `payload`。
6. 下载同轮原始 GCT，以 `=5381;` 定位哈希函数：向前找最近的 `function ` 并按花括号提取完整函数，再取紧随其后的 guard 函数。按 JavaScript int32、UTF-16 code unit 和 `Function.prototype.toString()` 原文语义计算 `biht`；不要要求 `var e=5381` 紧跟函数左花括号。
7. 图片识别后必须应用当前坐标映射公式；不要把 `gap_x` 直接作为 `setLeft`。`ddddocr` 返回 `target_x=0` 时优先取有效的 `target[0]`。
8. 生成轨迹并按轨迹时间真实等待，但不要擅自把逐点轨迹加入 `wPayload`。当前滑块组件提交的是 `setLeft/passtime/userresponse`，轨迹用于时序证据和本地归档。
9. 用 Python 生成随机 16 字节 ASCII hex AES key，执行 AES-CBC-PKCS7；再用已验证 GT4 公钥做 RSA-PKCS1-v1_5，拼接两个 hex。RSA modulus 无法从当前字符串表稳定提取时，允许使用模板中的已验证公钥，但必须通过新 `/verify` 确认未轮换。
10. 首轮成功后再并行跑两轮新 lot。三轮均检查 `status == "success"`、`data.result == "success"`、`fail_count == 0`；不要以固定 `w` 长度作为正确性证据。

最短命令：

```bash
python scripts/gt4_pure_replay.py \
  --captcha-id <captcha_id> \
  --bundle <当前 gcaptcha4.js>
```

## 无感（ai）

用于官方 Demo 切到“一键通过/无感验证”，或 `/load` 请求/响应明确出现 `risk_type=ai`、`captcha_type=ai` 的场景。该模式是验证层协议，不需要图片识别、滑动轨迹、点选坐标或真实等待。

### 识别信号

- `/load` URL 含 `risk_type=ai`，响应 `data.captcha_type == "ai"`。
- 响应无 `bg/slice/imgs/ques`，但含 `pow_detail/payload/process_token/payload_protocol/pt/gct_path`。
- 初始化阶段或点击前后会自动发 `/verify`，成功后 `seccode` 含 `pass_token/gen_time/captcha_output`。

### 标准流程

1. `GET /load`：`callback`、`captcha_id`、`challenge`、`client_type=web`、`risk_type=ai`、`lang=zh`，保存 JSONP 和 `captcha_v4_user`。
2. 下载同轮 `gct_path` 原始源码，按“GCT 与 `biht`”章节计算 `biht`，不要用 beautify 版本。
3. 按 `pow_detail` 生成 `pow_msg/pow_sign`，明文仍为 `version|bits|hashfunc|datetime|captcha_id|lot_number||nonce`。
4. 从当前 `gcaptcha4.js` 解析 `_lib` 固定字段和 `lib._abo` lot rule；2026-07-26 官方 Demo 样本为 `YYhg=BjI0` 与 `n[1:4] -> n[24:27]`，但仍必须从当前 bundle 动态提取。
5. 组装无感 `wPayload`，字段顺序与浏览器实抓一致：

```python
w_payload = {
    "device_id": "",
    "lot_number": lot_number,
    "pow_msg": pow_msg,
    "pow_sign": pow_sign,
    "geetest": "captcha",
    "lang": "zh",
    "ep": "123",
    "biht": biht,
    "gee_guard": gee_guard,
    **fixed_fields,
    **lot_fields,
    "em": em,
}
```

6. `w` 加密与滑块/文字点选相同：`AES-CBC-PKCS7(compact_json, random16_ascii_hex, iv=0*16) + RSA-PKCS1_v1_5(random16_ascii_hex)` 的 hex 拼接。
7. `GET /verify` 使用同轮 `lot_number/payload/process_token/payload_protocol/pt`，`risk_type=ai`。仅当 `status == "success"` 且 `data.result == "success"` 算通过。
8. 如果目标是官方 Demo，还可把 `seccode + captcha_id` 回放到 `/demo/login`；`demo_login.result == "success"` 且 `captcha_args.used_type == "ai"` 是业务门证据。

### 可直接复用

```bash
python scripts/gt4_ai_pure.py \
  --captcha-id <captcha_id> \
  --bundle <当前 gcaptcha4.js> \
  --rounds 1

python scripts/gt4_ai_pure.py \
  --captcha-id <captcha_id> \
  --bundle <当前 gcaptcha4.js> \
  --demo-login
```

依赖：`requests`、`pycryptodome`。不需要 `ddddocr`、`Pillow`、Node、iv8、ExecJS、jsdom 或浏览器。

### ai 高频排查

1. 把滑块字段 `setLeft/passtime/userresponse` 加进 `wPayload`：字段集合与浏览器不一致，可能导致失败。
2. 省略 `device_id:""`：浏览器明文包含空字符串，不能删。
3. 用 `risk_type=slide/word` 的 `/load` 材料提交 `risk_type=ai`：同轮状态断裂。
4. `challenge` 可用 UUID，但 `lot_number/payload/process_token` 必须来自同一个 `/load` 响应。
5. `fail_count` 在成功响应里可能为 `null` 或缺省；通过判据以 `status/result` 和业务门为准。

## Bundle 更新故障判定

出现以下组合时，优先判断为客户端 bundle 元数据轮换，而不是依赖、OCR 或网络问题：

- `/load` 成功，图片可识别。
- PoW 和 `w` 均能生成，`/verify` HTTP/JSONP 正常。
- 外层 `status` 是 `success`，但 `data.result` 连续为 `forbidden`，通常 `fail_count == 0`。
- 更换距离后仍稳定 `forbidden`。

如果用户已经提供最新 bundle，不必先启动浏览器。先离线对比旧、新 bundle 顶部预置字段和 webpack 模块结构。

## 动态字段来源

GT4 bundle 顶部会在进入主模块前写入两组元数据：

- `window._lib`：直接并入 `wPayload` 的固定字段，但字段名和值会随 bundle 轮换。
- `window.lib._abo`：根据 `lot_number` 生成附加字段的表达式映射。

已验证轮换样本（只能作版本证据，禁止写死）：

```text
更早 fixedFields: {"ZAhG":"MwHu"}
2026-07 中期 fixedFields: {"jCpk":"yZ7D"}
2026-07-23 fixedFields: {"YYhg":"BjI0"}  # static v1.9.6-1db46d

更早 lot rule:
  (n[17:18]+n[9:10])+.+(n[16:19])+.+(n[23:30]) -> n[10:15]
2026-07 中期 lot rule:
  n[20:20]+n[8:8]+n[11:11]+n[30:30] -> n[16:21]
2026-07-23 lot rule:
  n[1:4] -> n[24:27]
```

这些值只能作为版本样本，不应继续写死在 Node/vm 实现中。加载当前 bundle 后直接读取 `_lib` 和 `lib._abo`。纯 Python 从当前 `code.js` 文本解析同一组字段。

## 稳健暴露 Webpack Require

旧提取脚本把入口表达式中的字符串表索引写死为 `(20)`；新版索引变为 `(51)` 后，替换不再命中。应匹配整个 `i(i[...]=16)` 结构：

```js
function loadBundle(bundlePath) {
  let code = fs.readFileSync(bundlePath, 'utf8');
  code = code.replace(
    /i\(i\[[^\]]+\]\s*=\s*16\)/,
    '(globalThis.__req = i, {})'
  );

  const ctx = { console, setTimeout, clearTimeout };
  ctx.globalThis = ctx;
  ctx.global = ctx;
  ctx.self = ctx;
  ctx.window = ctx;
  ctx.navigator = {};
  ctx.document = {};
  vm.createContext(ctx);
  vm.runInContext(code, ctx, { timeout: 10000, filename: bundlePath });

  return {
    req: ctx.__req,
    fixedFields: ctx._lib || {},
    lotRules: (ctx.lib && ctx.lib._abo) || {},
  };
}
```

本次新旧 bundle 的模块数均为 61，已确认的 helper 为：

- `req(25).default(...)`：PoW。
- `req(27).default.load({type: 'gt4'})`：`gee_guard`。
- `req(31).default(compactJson, {options: {pt: '1'}})`：`w` 加密。
- `req(60).default([], em)`：填充 `em`。

当前 PoW 模块的实测参数顺序不能按字段名猜测：

```js
const pow = req(25).default(
  data.lot_number,
  captchaId,
  data.pow_detail.hashfunc,
  data.pow_detail.version,
  Number(data.pow_detail.bits),
  data.pow_detail.datetime,
  ''
);
```

当前 `gee_guard` 输出为 `{"roe":{"aup":"3","sep":"3","egp":"3","auh":"3","rew":"3","snh":"3","res":"3","cdc":"3"}}`，`em` 输出为 `{"ph":0,"cp":0,"ek":"11","wd":1,"nt":0,"si":0,"sc":0}`。这些模块编号和结果只是当前版本证据；后续升级仍应检查导出类型和函数特征，不能无条件假设。

## GCT 与 `biht`

`/load` 返回的 `gct_path` 必须按本轮地址下载。GCT 会导出 `_gct`，对 `{geetest:'captcha', lang:'zh', ep:'123'}` 增加 `biht`。当前实测 `typeof payload.biht === 'string'`，值形如 `"1426265548"`；保留 GCT 写入的原始类型。

当前 GCT 的 `biht` 不是普通静态配置，而是对两个函数的 `Function.prototype.toString()` 原文做 5381 风格哈希后得到。格式化、beautify 或改写 GCT 会改变函数原文，从而生成不同的 `biht`；本次原始 minified GCT 计算结果是 `1426265548`，格式化副本曾计算出不同值。

纯 Python 路径可以不执行 GCT：从原始源码中提取包含 `var e=5381` 的哈希函数及紧随其后的 guard 函数，按 JavaScript `int32`、左移和 UTF-16 code unit 语义复现哈希。不要把 `1426265548` 长期写死为跨版本常量。

## 通用 Lot Rule 解析

规则中的 `n[a:b]` 是零基、包含末端的切片。`+` 表示字符串拼接，解析结果中的 `.` 表示嵌套对象路径。

```js
function resolveLotExpression(expression, lotNumber) {
  return expression
    .replace(/n\[(\d+):(\d+)\]/g, (_, start, end) =>
      lotNumber.slice(Number(start), Number(end) + 1)
    )
    .replace(/\+/g, '');
}

function lotExtra(lotNumber, rules) {
  const result = {};
  for (const [keyExpression, valueExpression] of Object.entries(rules)) {
    const path = resolveLotExpression(keyExpression, lotNumber).split('.');
    const value = resolveLotExpression(valueExpression, lotNumber);
    let target = result;
    path.forEach((key, index) => {
      if (index === path.length - 1) target[key] = value;
      else target = target[key] || (target[key] = {});
    });
  }
  return result;
}
```

组装时使用：

```js
const wPayload = {
  setLeft,
  passtime,
  userresponse,
  device_id: '',
  lot_number: data.lot_number,
  pow_msg: pow.pow_msg,
  pow_sign: pow.pow_sign,
  geetest: 'captcha',
  lang: 'zh',
  ep: '123',
  biht,
  gee_guard,
  ...fixedFields,
  ...lotExtra(data.lot_number, lotRules),
  em,
};
```

## 纯 Python 路径

纯 Python 不需要 iv8、Node、ExecJS 或浏览器环境。`code.js` 可以只作为文本数据源，不执行其中的 JavaScript：

1. 提取顶部 `decodeURI(...)` 字符串和循环 XOR key，解出字符串表。
2. 从 `_lib/lib._abo` 初始化段读取字段名、字符串表索引和 lot rule。
3. 从字符串表选择当前 RSA modulus；找不到时才使用已验证公钥兜底。
4. 从本轮原始 GCT 源码计算 `biht`。
5. Python 生成 PoW、`gee_guard`、`em`、AES key、AES ciphertext 和 RSA encrypted key。

实现时优先直接使用 `scripts/gt4_pure_replay.py`，下面内容用于理解和排错，不要每个目标重新手写一次。

当前规则必须从 bundle 解析，不要手写。2026-07-23 样本对应：

```python
# fixedFields: {"YYhg": "BjI0"}
# lotRules: {"n[1:4]": "n[24:27]"}  -> key=lot[1:5], value=lot[24:28]
w_payload['YYhg'] = 'BjI0'
w_payload[lot_number[1:5]] = lot_number[24:28]
```

当前图片识别要兼容 `ddddocr` 同时返回占位 `target_x=0` 和有效 `target=[x1,y1,x2,y2]` 的情况：

```python
result = detector.slide_match(slice_bytes, bg_bytes, simple_target=True)
target = result.get('target')
gap_x = int(target[0]) if target and int(target[0]) > 0 else int(result['target_x'])
```

当前纯 Python `w` 核心：

```python
aes_key = secrets.token_hex(8).encode()
compact = json.dumps(w_payload, ensure_ascii=False, separators=(',', ':')).encode()
aes_hex = AES.new(aes_key, AES.MODE_CBC, iv=b'0000000000000000').encrypt(
    pad(compact, AES.block_size)
).hex()
rsa_hex = PKCS1_v1_5.new(public_key).encrypt(aes_key).hex()
w = aes_hex + rsa_hex
```

本次验证中 RSA 公钥、AES-CBC 方式、PoW 算法和 `userresponse` 生成方式未发生变化。仍需以服务端结果为准，不要仅凭静态 diff 宣称兼容。

## 高频排查

1. 只替换了 bundle 文件，但 loader 仍读取旧文件名：运行的仍是旧算法。
2. require 暴露正则写死字符串表索引：`ctx.__req` 不存在或仍执行入口模块。
3. 只替换加密模块，不更新 `_lib/lib._abo`：`w` 长度正常但 `/verify` 返回 `forbidden`。
4. 把动态字段长期硬编码：下一次小版本轮换会再次失效；Node/vm 应运行时提取。
5. 官方 Demo 可能按风控分配 `svg_seed` 点选，不等于直接请求 `risk_type=slide` 的协议发生变化；不要用 Demo 出现点选来否定滑块 `/load` 样本。
6. `ddddocr` 的 `target_x=0` 可能只是占位值；若 `target[0] > 0`，应优先使用 `target[0]`，否则会提交 `setLeft=0` 并得到 `result=fail, fail_count=1`。
7. GCT 下载后先 beautify 再计算 `biht`：函数 `toString()` 原文已变化，结果不可信；保留 raw 和 formatted 两份时只能用 raw 参与计算。
8. `status == "success"` 只表示请求被处理，不表示验证通过；必须检查 `data.result`。
9. 最终至少连续验证 Node/vm/iv8 路径 3 次；纯 Python 路径若存在，也至少验证 1 次真实 `/verify` 成功。
10. Python `requests` 在 `/load` 成功后下载 `static.geetest.com` 图片报 `ProxyError/RemoteDisconnected`：先检查环境代理；协议脚本可按环境使用 `session.trust_env = False`，不要误判为图片 URL 或 token 失效。
11. Node 22 的 `globalThis.navigator` 可能是只读 getter；不要直接 `Object.assign(globalThis, {navigator:{}})`，应使用独立 `vm.createContext()`。
12. `w` 长度会随紧凑 JSON 长度变化，不要把某次的 `1472` 或其他长度作为正确性判据；只检查十六进制格式、RSA 尾段长度和最终服务端结果。
13. `passtime` 不只是 payload 字段。生成参数后必须真实 `sleep(passtime / 1000)` 再请求 `/verify`，避免声明时间超过真实请求时序。
14. PoW 使用 `/load` 的长 `payload` 参与明文：当前版本会生成错误的 `pow_msg`；应确认 lot number 后是两个连续分隔符 `||`。
15. 用固定字符窗口读取 bundle 开头：混淆字符串表本身可能超过窗口，导致 `_lib/lib._abo` 明明存在却解析失败；按 lot rule 的明文位置反向定位初始化段。
16. GCT 正则只匹配 `function x(t){var e=5381`：当前 GCT 在 `5381` 前还有控制流变量，会误报找不到；先搜索 `=5381;` 再做函数边界提取。

## 文字点选（word）

用于官方 Demo / 业务站分配到 `risk_type=word` 时的纯协议复现。加密壳与滑块共用；**答案字段编码不同**。

### 识别信号

- `/load` 带 `risk_type=word` 或响应 `captcha_type=word`。
- 响应含 `imgs`（背景图）和 `ques`（目标字小图列表，顺序即点击顺序）。
- 没有滑块 `bg/slice`，不要套 `setLeft`。
- 浏览器 `gcaptcha4.js` 组装函数 `$_BBFB` 会把 `passtime/userresponse` 与 `device_id/lot_number/pow_*` 合并后再加密。

### 标准流程

1. `GET /load`：`callback`、`captcha_id`、`client_type=web`、`risk_type=word`、`pt=1`、`lang=zho`。
2. 下载同轮 `imgs`、`ques[]`、`gct_path`；保留 `lot_number/payload/process_token/pow_detail/pt`。
3. 识别（优先复用高成功率参考逻辑，见 `scripts/gt4_word_pure.py` 的 `solve_word_reference`）：
   - `ddddocr>=1.6.1`（已验证 1.5.6 明显更差）。
   - ques：优先 `invert(alpha) + autocontrast + resize(128)`，取第一个 CJK 字。
   - 背景：`det=True` 出框后，对 crop 与高色度 mask 做 -40°~40°/10° 多角度 OCR，形成候选字集合。
   - 匹配：先 exact 唯一锁定；剩余用 SIFT 特征分；SIFT 弱时再用左偏旁 radical 兜底。
   - 不要只做单次 classification + 贪心最近点。
4. 坐标编码（CDP 断点实抓，禁止再写成比例+时间戳）：

```python
userresponse = [
    [round(x / width * 10000), round(y / height * 10000)]
    for x, y in centers  # 原图像素中心，按 ques 顺序
]
```

5. `passtime` 取 1200–2500，真实 `sleep(passtime/1000)` 后再 `/verify`。
6. `wPayload` 字段顺序与浏览器一致：

```python
w_payload = {
    "passtime": passtime,
    "userresponse": userresponse,   # [[int,int], ...] 无 per-click t
    "device_id": "",                 # 空字符串也要写；不要省略
    "lot_number": lot_number,
    "pow_msg": pow_msg,
    "pow_sign": pow_sign,
    "geetest": "captcha",
    "lang": "zh",
    "ep": "123",
    "biht": biht,                   # 本轮原始 GCT
    "gee_guard": gee_guard,
    **fixed_fields,                 # 如 YYhg=BjI0
    **lot_fields,                   # lotRules 派生
    "em": em,
}
```

7. `w` 加密与滑块相同：`AES-CBC-PKCS7(compact_json, random16, iv=0*16) + RSA-PKCS1-v1_5(random16)` 的 hex 拼接。
8. `GET /verify` 使用同轮 `lot_number/payload/process_token/pt`，`risk_type=word`。仅当 `status=="success"` 且 `data.result=="success"` 且 `fail_count==0` 算通过。

### 可直接复用

- `scripts/gt4_word_pure.py`：纯 Python word `/load -> OCR/匹配 -> PoW/GCT/AES/RSA -> /verify`。
- `scripts/gt4_word_run.py`：多轮验收包装。
- 加密/元数据提取可复用滑块侧 `scripts/gt4_pure_replay.py` 的 PoW/GCT/AES/RSA 与 bundle 解析。

```bash
# 需要当前 gcaptcha4.js；官方 Demo captcha_id 可作联调
python scripts/gt4_word_pure.py \
  --captcha-id <captcha_id> \
  --bundle <当前 gcaptcha4.js> \
  --captcha-user <浏览器 captcha_v4_user 可选> \
  --rounds 3

python scripts/gt4_word_run.py
```

依赖：`requests`、`ddddocr>=1.6.1`、`Pillow`、`pycryptodome`、`opencv-python`、`numpy`、`scipy`。

### word 高频排查

1. 把 `userresponse` 写成 `[[x/w, y/h, t], ...]`：会稳定 `result=fail`。正确是 `round(ratio*10000)` 整数对，**无时间戳**。
2. 漏写 `device_id:""`：字段集合与浏览器不一致。
3. 用 `lang=zh` 请求 `/load` 而浏览器实际是 `lang=zho`：优先对齐浏览器参数。
4. `ddddocr==1.5.x`：ques/背景艺术字误识高；升到 `1.6.1` 并用 default+beta 投票。
5. 识别对了 2/3、有一个点错：仍会 `fail_count=1`；必须以服务端结果为准，不要只看 OCR 自洽。
6. 成功样本 `w_len` 常见 1472，但长度会随 compact JSON 变化，不能当正确性判据。
7. 协议壳已用浏览器明文完整回放验证 `result=success`。
8. 接入参考识别逻辑后，再加“仅提交全 `ocr-exact`、低置信换题”策略，实测可到 12/12。
9. 生产建议：`require_high_confidence=True`，且 `methods` 全为 `ocr-exact` 才发 `/verify`；否则重新 `/load`。
10. 不要退回通用 OCR 贪心匹配；参考识别主路径已在 `solve_word_reference`。

### 取证明文

浏览器 `JSON.stringify` 往往抓不到闭包内组装。优先：

1. CDP 断在 `gcaptcha4.js` 的 `$_BBFB` / `device_id` 合并附近。
2. 单步到 payload 含 `pow_msg` 后导出完整对象。
3. 用导出的 `userresponse/passtime/pow_*` 做离线加密回放，确认壳正确后再调识别。

## 本次验证证据

- 修复前：连续 5 次 `status=success, result=forbidden`。
- 修复后：模块复用的 iv8 流程连续 3 次 `result=success, fail_count=0`。
- 不执行任何 JavaScript 的纯 Python 流程真实返回 `result=success, fail_count=0`。
- 2026-07 浏览器无关 Python + Node VM 路径连续三轮成功：原图 `gap_x=182/197/209`，映射 `setLeft=160/173/184`，三轮均为 `status=success, result=success, fail_count=0`。
- 2026-07 纯 Python 路径连续三轮成功，全程未调用 Node/JS 引擎/浏览器：原图 `gap_x=219/100/215`，映射 `setLeft=193/87/189`，动态 `biht="1426265548"`，三轮均为 `status=success, result=success, fail_count=0`。
- 2026-07-23 bundle 轮换（`v1.9.6-1db46d`，`fixedFields={"YYhg":"BjI0"}`，`lotRules={"n[1:4]":"n[24:27]"}`）后连续 `forbidden`；替换最新 `gcaptcha4.js` 后 Node helper 与纯 Python 均恢复：`result=success, fail_count=0`（helper 1 轮 + pure 3 轮）。
- 2026-07-26 GT4 **无感 ai**（官方 Demo 一键通过）：
  - 浏览器 CDP 断在 `$_BBFB` 内部加密前，实抓 `wPayload` 不含 `setLeft/passtime/userresponse`，含 `device_id:""`、`pow_msg/pow_sign`、`biht="1426265548"`、`gee_guard`、`YYhg="BjI0"`、`lot[1:5] -> lot[24:28]`、`em`。
  - 纯 Python `scripts/gt4_ai_pure.py` 一轮 `/verify` 返回 `status=success, result=success`，`seccode` 含 `pass_token/gen_time/captcha_output`。
  - 同脚本 `--demo-login` 回放官方 `/demo/login` 返回 `result=success`，`captcha_args.used_type="ai"`，`fail_count=0`。
- 2026-07-26 GT4 **文字点选 word**：
  - CDP 抓到明文 `userresponse=[[1038,3033],[8129,6676],[2636,5678]]`（`round(x/w*10000)`），含 `device_id:""`。
  - 用该明文纯 Python 加密回放：`result=success, fail_count=0`。
  - `ddddocr 1.6.1` + default/beta 投票后自动多轮约 `3/8` 成功；协议壳已通，剩余波动主要在识别排序。
- 2026-07-26 GT4 **消消乐 match**（官方 Demo）：
  - Cloak 实抓 `/load` 为 `risk_type=match&lang=zh`，响应 `captcha_type="match"`，`ques` 为 3x3 数字矩阵，当前 bundle `v1.9.6-1db46d`。
  - 格式化 `gcaptcha4.js` 只能用于阅读；纯 Python 解析 `_lib/lib._abo` 必须保存 raw bundle，否则找不到顶部 `decodeURI(...)` 字符串表。
  - 当前动态字段仍为 `fixedFields={"YYhg":"BjI0"}`、`lotRules={"n[1:4]":"n[24:27]"}`，`biht="1426265548"`，但三者均从当前 raw bundle/GCT 动态计算。
  - 纯 Python `/load -> solve_match_puzzle -> PoW/GCT/AES/RSA -> sleep -> /verify` 一轮 + 连续三轮 fresh challenge 均返回 `status=success, result=success, fail_count=0`；成功样本 `w_length=1440` 仅作版本证据。
- 2026-07-27 GT4 **五子棋 winlinze**（官方 Demo）：
  - Chrome 实抓 `/load` 为 `risk_type=winlinze&lang=zh`，响应 `captcha_type="winlinze"`，`ques` 为 5x5 数字矩阵，当前 bundle `v1.9.6-1db46d`。
  - 源码确认明文 `userresponse` 顺序为非空棋子源格到目标空格，0 基 `[row,col]`，例如 `[[3,0],[1,2]]`。
  - Node helper 读取当前 raw bundle 与 raw GCT，动态字段为 `fixedFields={"YYhg":"BjI0"}`、`lotRules={"n[1:4]":"n[24:27]"}`，成功样本 `w_length=1440` 仅作版本证据。
  - `gt4_winlinze_replay.py` 一轮 + 连续三轮 fresh challenge 均返回 `status=success, result=success, fail_count=0`；官方 Demo 实测 `passtime=0` 仍可通过。
