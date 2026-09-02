# AI Drama Studio — 本机真实项目验收

> 适用架构：Localized Remake V1  
> 当前状态：**Runtime stack checker + 验收编排器已实现并有独立 Windows 契约测试；真实 H3 / Qwen / LatentSync / Audio Separator / 成片人工看听验收仍为 PENDING。**

## 1. 这一步验收什么

仓库内部 R7/R8/R9/R10/R10.1 已经有隔离 CI，但它不能证明用户本机的真实模型、GPU、素材和最终短剧质量。

本机最终验收必须走真实生产链：

```text
真实 Project
→ 自动准备
→ GenerationSegment
→ MiniMax H3
→ R9 QC / 自动重试
→ GenerationSelection
→ LatentSync
→ 目标对白 + 安全背景音
→ EpisodeOutput
→ 人工看听成片
```

验收工具只是现有 Runtime / 生产 API 的检查和编排器，不是另一套业务流水线。

它们不会：

```text
安装或猜测模型 Runtime
修改人物/场景/对白/时间轴业务真相
直接关闭 ReviewIssue
绕过 H3_QC / LIP_SYNC_QC
把脚本成功等同于人工成片验收成功
```

## 2. 前置 Runtime

完整本机验收要求以下服务都 READY：

```text
AI Drama Studio Backend
MiniMax H3 FL2VA
MiniMax H3 Ref2VA
Qwen3-VL
Qwen3-TTS
LatentSync 1.6
Audio Separator
```

当前默认端口：

```text
Backend          8000
Qwen3-VL         8001/v1（以 AI_DRAMA_VLM_BASE_URL 为准）
H3 FL2VA         30010
H3 Ref2VA        30011
Qwen3-TTS        7861
LatentSync       7862
Audio Separator  7863
```

说明：正式生产在 Audio Separator 不可用时允许安全降级为 `TARGET_DIALOGUE_ONLY_FALLBACK`；但“完整本地栈验收”仍要求 Audio Separator READY，以便真正验证 R10.1。

具体 Runtime 安装/启动边界见 `docs/INSTALL_AND_RUN_WINDOWS.md`。仓库对 Audio Separator 提供完整 setup/start/check；对 H3、Qwen3-VL、Qwen3-TTS、LatentSync 不会提供未经当前环境验证的猜测启动参数。

## 3. Runtime stack 预检

Backend 和模型服务启动后，先在仓库根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check_local_remake_runtime_stack.ps1
```

它只检查：

```text
Backend
H3 FL2VA
H3 Ref2VA
Qwen3-VL
Qwen3-TTS
LatentSync
Audio Separator
```

全部必须显示 `READY` 才进入完整真实项目验收。

机器可读结果：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check_local_remake_runtime_stack.ps1 -Json
```

退出码：

```text
0  READY
3  BLOCKED
```

这个 checker 是只读工具：不下载模型、不启动服务、不改项目数据。

Qwen3-VL 的 `/models` 在部分本地 OpenAI-compatible server 上会返回模型绝对路径，而生产请求可能使用配置 alias。checker 会把 exact model-id mismatch 作为诊断信息，不会因为这个差异制造假 blocker；真正的门禁仍是明确配置 + endpoint 可达。

## 4. Project 只读检查

Runtime 全 READY 后，再检查具体 Project 当前状态：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_real_project_acceptance_v1.ps1 `
  -ProjectId PROJECT_xxx
```

这一步不会启动新的重任务，只读取当前状态。

需要机器可读结果时：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_real_project_acceptance_v1.ps1 `
  -ProjectId PROJECT_xxx `
  -Json
```

## 5. 执行 / 断点续跑真实生产链

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_real_project_acceptance_v1.ps1 `
  -ProjectId PROJECT_xxx `
  -Run
```

`-Run` 是断点续跑，不是每次从头跑：

```text
已有 Current GenerationSegment
→ 跳过自动准备

已有完整 GenerationSelection
→ 跳过 H3

已有完整 PostProduction + EpisodeOutput
→ 不再启动任何重任务
```

如果自动准备 / H3 QC / Lip Sync 产生真实 `ReviewIssue`，脚本立即返回 `NEEDS_REVIEW`。请到现有 Review Center 修改真实业务数据，然后重新执行同一个命令。

## 6. Project Result 与退出码

```text
0  READY_FOR_MANUAL_ACCEPTANCE
2  NEEDS_REVIEW
3  RUNTIME_BLOCKED
4  PIPELINE_FAILED
5  NOT_READY
```

含义：

- `READY_FOR_MANUAL_ACCEPTANCE`：机器链已经完整形成当前 Selected Output、PostProduction 和 EpisodeOutput；**仍然不是最终人工 PASS**。
- `NEEDS_REVIEW`：存在真实人工复核问题，必须在产品 Review Center 处理。
- `RUNTIME_BLOCKED`：完整验收所需本地 Runtime 尚未全部 READY。
- `PIPELINE_FAILED`：现有生产任务或 HTTP 链执行失败，应先修真实运行问题。
- `NOT_READY`：当前没有人工问题，但生产结果尚未覆盖完整项目，例如 QC 仍等待模型或输出尚未齐全。

## 7. 最终人工看听清单

只有看完真实导出的 Episode MP4/SRT 后，才能判定真实项目验收是否通过。

重点检查：

```text
[ ] 全剧 TargetCharacter 身份稳定，没有原演员脸/身体身份泄漏
[ ] LOCALIZE 场景符合目标地区，KEEP 场景没有明显地域冲突
[ ] 原剧动作顺序、走位、构图、运镜和叙事节奏被正确保留
[ ] 目标对白语义正确、自然，语言/地区表达符合项目设置
[ ] 目标人物声音稳定，同一角色跨镜头没有明显音色漂移
[ ] 可见说话人的口型正确；多人镜头没有同步到错误人物
[ ] 没有残留原语言对白
[ ] SOURCE_BACKGROUND_SAFE 中环境声/BGM/SFX 可用且不盖住目标对白
[ ] 与 TARGET_DIALOGUE_ONLY_FALLBACK 对比后，背景增强确实提高质量
[ ] 因目标语音时长产生的 TRIM / EXTEND / 反应镜承接没有明显卡顿
[ ] 字幕内容、时间、跨 Segment 去重正确
[ ] 整集 MP4 可完整播放，镜头拼接、音轨、SRT 均无断裂
```

建议至少额外强制制造并验证一次：

```text
H3_QC 模糊/失败 → Review Center → 修正/重试 → Selected Output
LIP_SYNC_QC 多人身份模糊 → Review Center → 修正/重试 → PostProduction
```

## 8. 相关文件

```text
scripts/check_local_remake_runtime_stack.py
scripts/check_local_remake_runtime_stack.ps1
scripts/run_real_project_acceptance_v1.py
scripts/run_real_project_acceptance_v1.ps1
engine/tests/v2/test_local_remake_runtime_stack_v1.py
engine/tests/v2/test_real_project_acceptance_v1.py
.github/workflows/real-project-acceptance.yml
```

Dedicated Windows tooling CI validates Python compilation, PowerShell parsing and contract gates for both tools. It intentionally does not install or fake the heavy local model environments.

现阶段不要因为验收工具存在就把以下状态改成 PASS：

```text
LOCAL H3 / QWEN / LATENTSYNC / AUDIO-SEPARATOR / REAL PROJECT ACCEPTANCE = PENDING
```

真正改变这个状态的唯一依据是：**用户本机真实项目完整跑通，并对最终成片完成看听验收。**
