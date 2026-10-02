#!/usr/bin/env python3
"""Aliyun Captcha V3 缺口检测器 + 真人轨迹拖拽 —— 参考实现（逐字抽取，未改写）

出处: zcode-api/tools/signup_drive.py  (2026-10-01 版本)
本文件下方 valley_pick / valley_pick_from / detect_gap / drag_for_gap / human_drag
五段代码**逐字**复制自该源文件，仅去掉采集器专有逻辑。用途: 作为本 skill 的
规范实现与调参基线。

依赖: numpy, opencv-python (cv2)

关键结论（推导见 SKILL.md）:
  - 检测器是**多信号投票**: lap > hf > lapc > ring > health（实测命中率排序）
  - 峰值选择 = 平滑后"最宽显著低谷中心"（valley_pick），不是 argmin
  - 拼图块位移 P 与鼠标拖拽 D 是**非线性**的: P = a·D² + b·D + c，必须反解
  - 未过时 SDK ~2s 自动换题 ⇒ 同一轮的检测结果**不可跨轮复用**
  - 任何像素匹配类检测器（MSE/SAD/NCC/模板）必错: INPAINTING 把碎片像素
    填回了背景，洞里已不存在碎片。它们只能当兜底。
"""

# ==================== 常量 (源文件 34-53 行) ====================
    print("usage: SIGNUP_PASSWORD=... python signup_drive.py <name> <email>   (or SIGNUP_* env)")
    sys.exit(2)


def log(*a):
    print(*a, flush=True)


# 环形比值的上下留白(行)。太小 → 周围也落在洞里;太大 → 混进无关结构。
RING_PAD = 8

# 谷底提取参数(2026-10-01 在 117 个未换题样本上扫参得出, 见 tools/_bench3.py)。
# frac=0.2 / sigma=3.0 是"平滑后最宽低谷中心"这一取法的最优点。
VALLEY_FRAC = 0.20
VALLEY_SIGMA = 3.0
VALLEY_MINW = 6


def data_url_bytes(u: str) -> bytes:
    return base64.b64decode(u.split(",", 1)[1])

# ==================== 谷底提取 valley_pick (源文件 56-112 行，逐字) ====================
def valley_pick(c, frac=VALLEY_FRAC, minw=VALLEY_MINW, sigma=VALLEY_SIGMA):
    """从得分曲线里取**最宽的显著低谷中心**(越小越像洞的曲线用)。

    为什么不是 argmin / 容差簇中位数(旧取法)——
    2026-10-01 在 117 个未换题手拖真值样本上实测, **同一个信号换个取法, 命中率翻倍**:

        lap  容差簇中位数 29.9%  →  最宽低谷 47.0%   (中位误差 46.6px → 6.2px)
        hf   32.5%                →  45.3%
        ring 27.4%                →  42.7%

    argmin 的毛病: 曲线在真值附近是**平台**不是尖峰(洞被 inpaint 填平后,
    洞内几列得分几乎相同), 平台里哪个 X 最小纯属噪声 → ±3px 起步的抖动。
    容差簇(1%)只是把抖动限制在榜首那一小撮里, 换个题就整撮跑偏。
    取"最宽低谷的中心"利用了"洞是一整段平坦区"这个**结构先验**, 天然抗噪。
    """
    c = np.asarray(c, dtype=np.float64)
    if c.size == 0:
        return 0.0
    k = cv2.GaussianBlur(c.astype(np.float32).reshape(1, -1), (0, 0), sigma).ravel() \
        if sigma > 0 else c.astype(np.float32)
    lo, hi = float(k.min()), float(k.max())
    if hi - lo < 1e-12:
        return float(np.argmin(c))
    low = k <= lo + (hi - lo) * frac
    runs, s = [], None
    for i, v in enumerate(low):
        if v and s is None:
            s = i
        elif not v and s is not None:
            runs.append((s, i - 1)); s = None
    if s is not None:
        runs.append((s, len(low) - 1))
    wide = [r for r in runs if r[1] - r[0] + 1 >= minw] or runs
    if not wide:
        return float(np.argmin(c))
    a, b = max(wide, key=lambda r: r[1] - r[0])
    return (a + b) / 2.0


def valley_pick_from(pairs, bgw, cw):
    """把 [(X, score)] 摊成稠密曲线再取最宽低谷。X 有缺口时按线性插值补齐。"""
    if not pairs:
        return 0.0
    n = max(0, bgw - cw) + 1
    curve = np.full(n, np.nan)
    for x, s in pairs:
        if 0 <= x < n:
            curve[x] = s
    if np.isnan(curve).all():
        return float(pairs[0][0])
    idx = np.arange(n)
    good = ~np.isnan(curve)
    if good.sum() >= 2:
        curve = np.interp(idx, idx[good], curve[good])
    else:
        curve = np.nan_to_num(curve, nan=float(pairs[0][1]))
    return valley_pick(curve)

# ==================== 缺口检测 detect_gap (源文件 115-331 行，逐字) ====================
def detect_gap(bg_b: bytes, pz_b: bytes) -> dict:
    bg = cv2.imdecode(np.frombuffer(bg_b, np.uint8), cv2.IMREAD_COLOR)
    pz = cv2.imdecode(np.frombuffer(pz_b, np.uint8), cv2.IMREAD_UNCHANGED)
    if bg is None or pz is None:
        return {"error": "decode failed"}
    bg_gray = cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY).astype(np.float64)

    if pz.ndim == 3 and pz.shape[2] == 4:
        alpha = pz[:, :, 3]
        mask = alpha > 128
        pz_gray = cv2.cvtColor(pz[:, :, :3], cv2.COLOR_BGR2GRAY).astype(np.float64)
    else:
        mask = np.ones(pz.shape[:2], dtype=bool)
        pz_gray = pz.astype(np.float64) if pz.ndim == 2 else cv2.cvtColor(pz, cv2.COLOR_BGR2GRAY).astype(np.float64)

    ys, xs = np.nonzero(mask)
    if len(ys) == 0:
        return {"error": "empty mask"}
    y0, y1, x0, x1 = int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())
    content = pz_gray[y0:y1 + 1, x0:x1 + 1]
    cw, ch = content.shape[1], content.shape[0]
    bgw = bg_gray.shape[1]

    # ---------------------------------------------------------------- MSE
    # ⚠ 这里曾写「掩码 RGB 均方差 —— **本场景唯一可靠的检测器**」，并把
    #   「MSE 峰 x=178 与背景完全对齐」当成证据。**已推翻**（见下方 RING 段的长注释）：
    #   本场景是 INPAINTING 抠物填洞题，碎片不在底图里，MSE 只是"背景里最像碎片的
    #   普通区域"，18 样本中位误差 68.5px。保留计算仅为兜底候选/对照，**不是主力**。
    # 仍然成立的一点：碎片是整条 bg 高的竖带，内容只在自己真实 y 区间 → y 对齐白送。
    rgb_pz = pz[:, :, :3].astype(np.float64)
    m3 = mask.astype(np.float64)[..., None]
    msum = max(float(mask.sum()), 1e-9)
    band = bg.astype(np.float64)
    mse_l = []
    for X in range(0, max(0, bgw - cw) + 1):
        reg = band[:, X:X + cw, :]
        if reg.shape[1] != cw:
            continue
        d = ((reg - rgb_pz) ** 2 * m3).sum()
        mse_l.append((X, float(d / msum)))
    mse_l.sort(key=lambda t: t[1])

    cmean = content.mean()
    cb = content - cmean
    cbb = float((cb * cb).sum())

    sad_l, ncc_l = [], []
    for X in range(0, bgw - cw + 1):
        reg = bg_gray[y0:y1 + 1, X:X + cw]
        if reg.shape != content.shape:
            continue
        sad_l.append((X, float(np.abs(reg - content).mean())))
        rb = reg - reg.mean()
        den = float(np.sqrt((rb * rb).sum() * cbb))
        ncc_l.append((X, float((rb * cb).sum() / den) if den > 0 else 0.0))
    sad_l.sort(key=lambda t: t[1])
    ncc_l.sort(key=lambda t: -t[1])

    # gradient (edge) matching — helps when the hole was inpainted
    def grad(im):
        gx = cv2.Sobel(im, cv2.CV_64F, 1, 0, ksize=3)
        gy = cv2.Sobel(im, cv2.CV_64F, 0, 1, ksize=3)
        return np.sqrt(gx * gx + gy * gy)

    bgg, pzg = grad(bg_gray), grad(pz_gray)
    cont_g = pzg[y0:y1 + 1, x0:x1 + 1]
    g_l = []
    for X in range(1, bgw - cw):
        reg = bgg[y0:y1 + 1, X:X + cw]
        g_l.append((X, float(np.abs(reg - cont_g).mean())))
    g_l.sort(key=lambda t: t[1])

    # ------------------------------------------------- RING(2026-10-01)
    # ⚠ 这一段上面/下面的注释曾经声称「RING 是本场景唯一可靠的检测器」并拿
    #   kitchen182 单样本(真值 182，ring 榜首簇 180..185)当证据。**那个结论是错的**，
    #   2026-10-01 用 15 个手过样本(真值 = 通过后 style.left，精确)实测推翻：
    #
    #   本场景恒为 CaptchaType=INPAINTING(实测 18/18)：服务端把底图里的**物体抠掉**
    #   再把洞 inpaint 填平，碎片就是那个物体(台灯/数字/瓶子/石像…)。
    #   → 碎片**根本不在底图里**，"洞内 == 碎片"这个前提不成立，
    #     MSE/SAD/NCC/GRAD/template-match 结构上就注定答错。
    #     (合成对照：从底图自己抠一块做模板，min/med = 0.000000 完美命中；
    #      真碎片 min/med 0.23~0.69 → 碎片确实不在图里。)
    #
    #   各方法中位误差(n=18)：grad_x 43.5 / sad 44.7 / **ring_center 48.6** /
    #   mse 68.5 / ncc 81.7。±5px 命中都只有 3~4/18。
    #
    #   RING 的"洞相对自身上下邻域平坦"也不成立：真值处 `inside/around`
    #   是最小值的 ≈4.4 倍，排名中位 ~24/270。15 个样本里只有 1 个排到第 1。
    #   所以 RING **不是可靠检测器**，只是"一筐烂里较好的那个"——保留它是因为
    #   失败重试免费(拖错 ~2s 自动换新题，见 [[zcode-captcha-free-retry]])，
    #   弱先验 + 无限重试仍可用；但别再把单样本巧合当成可靠性证据。
    #
    #   要真正做到"一次答对"只能上语义/ML 视觉("钟面少了哪个数字""谁手里少了东西")。
    bg_l = cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY).astype(np.float64)
    hol = mask[y0:y1 + 1, :cw]
    gx_ = np.abs(np.diff(bg_l, axis=1, prepend=bg_l[:, :1]))
    gy_ = np.abs(np.diff(bg_l, axis=0, prepend=bg_l[:1, :]))
    E = gx_ + gy_
    yA, yB = max(0, y0 - RING_PAD), min(bg_l.shape[0], y1 + 1 + RING_PAD)
    ring_l = []
    for X in range(0, max(0, bgw - cw) + 1):
        sub = E[y0:y1 + 1, X:X + cw]
        if sub.shape[1] != cw:
            continue
        inside = float(sub[hol].mean()) if hol.any() else float(sub.mean())
        around = float(E[yA:yB, X:X + cw].mean())
        ring_l.append((X, inside / (around + 1e-6)))
    ring_l.sort(key=lambda t: t[1])

    # argmin 的精度只有 ±3px，分数差常小于 0.3%(继续比大小是在比噪声)。
    # 榜首批仅留作诊断输出;实际取点已换成下面的 valley_pick(2026-10-01)。
    cl = []
    if ring_l:
        best = ring_l[0][1]
        cl = [x for x, s in ring_l if s <= best * 1.01]

    # ---------------------------------------------- HEALTH / LAP / HF
    # ⚠️ 2026-10-01 修的**静默 bug**: 本函数原样只返回 ring/mse/sad/ncc/grad,
    # 而下面的 `cands` 是按 gap["consensus"]、gap["health"] 取的 —— 键根本不存在,
    # 于是第一、二候选槽被静默跳过, 实际只用最弱的 grad/sad/mse/ncc 在猜
    # (G0 实测 8 轮 16 次全错)。现在把 login_drive.detect_gap 那一套原样搬进来,
    # 两处检测器必须**同源同结果**, 否则采集台和生产驱动会给出不同答案。
    #
    # health: 分母换**整条竖带**(而不是洞上下 8px 邻域), 采样多、猜错时不会离谱。
    health_l = []
    for X in range(0, max(0, bgw - cw) + 1):
        sub = E[y0:y1 + 1, X:X + cw]
        if sub.shape[1] != cw:
            continue
        inside = float(sub[hol].mean()) if hol.any() else float(sub.mean())
        health_l.append((X, inside / (float(E[:, X:X + cw].mean()) + 1e-6)))
    health_l.sort(key=lambda t: t[1])

    # lap: 同 ring 但换二阶 Laplacian(对"被抹平"更敏感)。
    L = np.abs(cv2.Laplacian(bg_l, cv2.CV_64F, ksize=3))
    lap_l = []
    for X in range(0, max(0, bgw - cw) + 1):
        sub = L[y0:y1 + 1, X:X + cw]
        if sub.shape[1] != cw:
            continue
        inside = float(sub[hol].mean()) if hol.any() else float(sub.mean())
        around = float(L[yA:yB, X:X + cw].mean())
        lap_l.append((X, inside / (around + 1e-6)))
    lap_l.sort(key=lambda t: t[1])

    # lapc: 同 lap 但分母换**整条竖带**(像 health 对 E 那样)。ring 只用 8px
    # 邻域采样太少, 猜错时错得远; 除以整列方差小得多。实测 41.0%(新取法)。
    lapc_l = []
    for X in range(0, max(0, bgw - cw) + 1):
        sub = L[y0:y1 + 1, X:X + cw]
        if sub.shape[1] != cw:
            continue
        inside = float(sub[hol].mean()) if hol.any() else float(sub.mean())
        lapc_l.append((X, inside / (float(L[:, X:X + cw].mean()) + 1e-6)))
    lapc_l.sort(key=lambda t: t[1])

    # hf: **高频**能量比(σ=0.4 高通)。inpaint 抹掉的正是最高频那一档。
    _G = bg_l
    _HF = np.abs(_G - cv2.GaussianBlur(_G, (0, 0), 0.4))
    hf_l = []
    for X in range(0, max(0, bgw - cw) + 1):
        sub = _HF[y0:y1 + 1, X:X + cw]
        if sub.shape[1] != cw:
            continue
        inside = float(sub[hol].mean()) if hol.any() else float(sub.mean())
        hf_l.append((X, inside / (float(_HF[:, X:X + cw].mean()) + 1e-6)))
    hf_l.sort(key=lambda t: t[1])

    # ------------------------- 各视角换用「最宽低谷」取法(2026-10-01)
    # 上面所有 *_x / *_center 都是「argmin+容差簇中位数」这条旧取法。实测在
    # 117 个未换题真值样本上, **同一个信号只换取法**:
    #     lap   29.9% → 47.9% (中位误差 46.6px → 5.3px)
    #     ring  27.4% → 44.4%
    #     lapc  新视角  41.0%
    #     hf    32.5% → 39.3%
    #     health 40.2% → 39.3%
    # 旧取法把"洞"当尖峰找, 但洞被 inpaint 抹平后洞内几列得分几乎相同, 是个
    # **平台**; 平台里谁最小纯属噪声。最宽低谷吃的是"洞是一整段平坦区"这个
    # 结构先验, 天然抗噪。
    lap_w = valley_pick_from(lap_l, bgw, cw)
    lapc_w = valley_pick_from(lapc_l, bgw, cw)
    hf_w = valley_pick_from(hf_l, bgw, cw)
    ring_w = valley_pick_from(ring_l, bgw, cw)
    health_w = valley_pick_from(health_l, bgw, cw)

    # 共识融合: 一致(|Δ|<=15)时取均值降方差; 不一致时取三者中位数做稳健估计
    # (ring 猜错时错得离谱, 均值会被带偏, 中位数抗得住)。
    if abs(ring_w - health_w) <= 15.0:
        consensus = (ring_w + health_w) / 2
    else:
        consensus = float(np.median([ring_w, health_w, lap_w]))

    return {
        "bg_w": bgw, "piece": {"x0": x0, "y0": y0, "cw": cw, "ch": ch},
        "ring": {"x": ring_w, "score": round(ring_l[0][1], 4) if ring_l else None,
                 "center": round(ring_w, 1), "cluster": len(cl),
                 "top5": [[a, round(b, 4)] for a, b in ring_l[:5]]},
        "health": {"x": health_w, "score": round(health_l[0][1], 4) if health_l else None,
                   "top5": [[a, round(b, 4)] for a, b in health_l[:5]]},
        "lap": {"x": lap_w, "score": round(lap_l[0][1], 4) if lap_l else None,
                "top5": [[a, round(b, 4)] for a, b in lap_l[:5]]},
        "lapc": {"x": lapc_w, "score": round(lapc_l[0][1], 4) if lapc_l else None,
                 "top5": [[a, round(b, 4)] for a, b in lapc_l[:5]]},
        "hf": {"x": hf_w, "score": round(hf_l[0][1], 4) if hf_l else None,
               "top5": [[a, round(b, 4)] for a, b in hf_l[:5]]},
        "consensus": round(consensus, 1),
        "mse": {"x": mse_l[0][0], "score": round(mse_l[0][1], 1),
                "top5": [[a, round(b, 1)] for a, b in mse_l[:5]]},
        "sad": {"x": sad_l[0][0], "score": round(sad_l[0][1], 2),
                "top5": [[a, round(b, 2)] for a, b in sad_l[:5]]},
        "ncc": {"x": ncc_l[0][0], "score": round(ncc_l[0][1], 4),
                "top5": [[a, round(b, 4)] for a, b in ncc_l[:5]]},
        "grad": {"x": g_l[0][0], "score": round(g_l[0][1], 2),
                 "top5": [[a, round(b, 2)] for a, b in g_l[:5]]},
    }


# ==================== 非线性标定 + Playwright 拖拽 (源文件 333-376 行，逐字) ====================
def drag_for_gap(gap_x: float) -> float:
    """把「拼图块需要走多远」换算成「鼠标需要拖多远」。

    **这是整条链路的真正症结**。滑块 thumb 与鼠标 1:1 跟手,但**拼图块不是** ——
    它走一条缓动曲线。老脚本假设 1:1(`dist = gap_x`),在这条曲线上永远拖不到位,
    表现就是「三个检测器都算对了位置,但每次都判失败」。

    2026-10-01 实测标定(同一谜题内按住不放,分 5 档测量):

        拖拽 D   拼图块位移 P   比值
          40         8        0.200
          80        28        0.350
         120        60        0.500
         160       103        0.644
         200       157        0.785

    二次拟合 P = 0.003527·D² + 0.086071·D − 1.2,五个点残差 ≤ 0.26px。
    这里反解出 D。曲线起点 P(0) = −1.2 → 负根,只有正根有意义。
    """
    a, b, c = 0.003527, 0.086071, -(1.2 + gap_x)
    disc = b * b - 4 * a * c
    if disc < 0:
        return gap_x  # 不该发生;退化成 1:1 好过崩
    return (-b + math.sqrt(disc)) / (2 * a)


def human_drag(page, start_x, y, dist, duration_ms=900):
    """Trusted drag: CDP-dispatched mouse events, eased with jitter."""
    page.mouse.move(start_x, y)
    time.sleep(0.06)
    page.mouse.down()
    time.sleep(0.05)
    steps = max(24, int(duration_ms / 22))
    for i in range(1, steps + 1):
        t = i / steps
        eased = 2 * t * t if t < 0.5 else 1 - pow(-2 * t + 2, 2) / 2
        jx = (random.random() - 0.5) * 1.1
        jy = (random.random() - 0.5) * 0.6
        page.mouse.move(start_x + eased * dist + jx, y + jy)
        time.sleep(0.008 + random.random() * 0.012)
    page.mouse.move(start_x + dist, y)
    time.sleep(0.15)
    page.mouse.up()

