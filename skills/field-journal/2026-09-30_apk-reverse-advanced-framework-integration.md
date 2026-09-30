# 工业级 APK 逆向与字节补丁体系集成（newliver666/apk-reverse 实战演进）

日期：2026-09-30
场景：Android APK 逆向与高级防护对抗体系升级 / 将 newliver666/apk-reverse 全套门禁、参考架构与自动化脚本并入 reverse-skill

## 背景与痛点

原 `skills/apk-reverse` 偏向基础工具调用（4 个指导文档，4 个 PS1/SH 脚本），在面对工业级加固、Flutter AOT、代码虚拟化（VMP/Java2C）、内核防护（KernelSU/raw svc）及复杂重打包陷阱时存在明显认知盲区：
1. **脱离层级盲目修改**：遇到服务端下发配置或虚拟化层时，盲目用 Jadx/smali 导出进行全局修改，导致 R8 优化破坏、文件膨胀及运行时静默闪退。
2. **缺乏严格门禁与止损法则**：缺乏 G1-G4 前置校验，常在未确定归属层（Java/Native/Dart/Server）时反复试错，消耗大量时间。
3. **工具链与自动化脚本匮乏**：缺少 Dart AOT 符号池扫描、VMP 差分分析测试基准、字节级等长精准补丁（dex_patch_bytes/dex_find_insn）等专用武器库。

## 集成方案与实施细节

将社区工业级成熟框架 `newliver666/apk-reverse` 完整深度整合：

1. **核心门禁与覆盖原则**：
   - **四大门禁（G1–G4）**：G1（交付形式与成本上限约束，严格区分为 Rebuilt APK / LSPosed / 本地 RPC 服务 / 分析报告）、G2（环境事实与能力清单 doctor.py/preflight.py）、G3（代码位置与归属层锁定）、G4（基线与控制组比对）。
   - **四项覆盖法则（R1–R4）**：测试语句先行、单变量控制组、拒绝无验证宣称、归属层不对立即止损。
   - **双击止损（Two-strike Rule）**：同一假设方向连续两次失败强行退回分类，绝不运行第 3 次变体。
2. **知识与避坑图谱**：
   - 扩充 40+ 专项参考文档（涵盖 `byte-level-patching.md`, `code-virtualization-and-custom-linkers.md`, `dart-aot.md`, `java2c-and-jni-sinking.md`, `signature-derived-keys.md`, `vmp-differential-analysis.md`, `lsposed-and-modules.md`, `kernel-and-environment-hardening.md` 等）。
   - 保留原平台 4 项基础参考（`android-advanced.md`, `apk-security-checklist.md`, `frida-bypass-kit.md`, `frida-cookbook.md`）。
3. **自动化脚本武器库**：
   - 引入 50+ 项专业脚本工具（包含 `dex_strings.py`, `dex_patch_bytes.py`, `dex_classdiff.py`, `dart_pool_strings.py`, `kernelsu_syscall_mask.py`, `vmp_diff_harness.py`, `dexpatch/` 等）。
   - 无缝保留平台原有 PowerShell 极速包装脚本（`decode.ps1`, `frida-run.ps1`, `rebuild-sign-install.ps1`, `manifest-summary.ps1`）。
4. **测试与协同校验通过**：
   - `python doctor.py --json` 验证本地工具链（GraalVM 21, Python 3.11, Jadx, Apktool, Rabin2, ADB 正常探测）。
   - `verify-routing-coherence.ps1` 校验 186 个路由基准全部通过（186/186 PASS）。
   - `refresh-tool-index.ps1` 刷新 42 项工具映射，无缝衔接 `tool-index.md` 与平台生态。
