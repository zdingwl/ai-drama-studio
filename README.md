# AI Drama Studio — Localized Remake V1

AI Drama Studio 是面向 Windows 本地 GPU 工作站的 **AI 短剧本土化重拍系统**。

它不是单纯做视频翻译，也不是只生成拉片报告。原短剧作为“导演参考”：系统理解原剧剧情、人物关系、动作、镜头、对白和节奏，然后用目标地区人物、必要的本土化场景、目标语言对白、目标人物声音和重新规划的时间轴，生成一部新的本土化短剧。

> 新开发者先读：`AGENTS.md` → `SKILL.md` → `docs/PROJECT_STATE.md` → `docs/CURRENT_IMPLEMENTATION_MANIFEST.md`
>
> Windows 安装/运行：`docs/INSTALL_AND_RUN_WINDOWS.md`
>
> 真实项目验收：`docs/REAL_PROJECT_ACCEPTANCE.md`

## 当前产品主线

```text
原短剧 / Episodes
→ Shot + Reference Clip
→ ASR / OCR / Qwen3-VL 内容理解
→ Character V10.1 / Scene / Prop
→ SourceDramaSnapshot
→ TargetCharacter + SceneLocalizationMapping
→ TargetDialogue + Qwen3-TTS + 真实目标语音时长
→ RemakeTimeline
→ GenerationSegment
→ H3 Context + 目标人物/场景参考
→ Local MiniMax H3 GenerationAttempt
→ Structural + Qwen3-VL Semantic QC
→ 自动重试
→ GenerationSelection / Selected Output
→ LatentSync 目标说话人口型
→ 目标对白 + 安全背景音 + 字幕
→ EpisodeOutput MP4 + SRT
→ 本土化短剧
```

核心规则：

- 人物始终替换成本土化目标人物；
- 场景支持 `AUTO / KEEP / LOCALIZE`；
- 原 Shot 时间不是最终时间，目标语言真实说话时长决定 RemakeTimeline；
- `Shot != GenerationSegment`，长/短镜头可以根据 H3 能力重新分段；
- `GenerationAttempt != 可交付镜头`，只有 `GenerationSelection` 能进入后期；
- 可见说话人才做口型，off-screen 对白不做无意义 Lip Sync；
- 多人镜头先定位目标说话人的脸，再做 ROI Lip Sync；
- 原语言音轨不能直接混入成片；背景音乐/环境音/SFX 必须先分离并再次硬抑制原语言对白窗口；
- Source ASR / OCR / Shot truth 下游不可篡改。

## 当前实现状态

| 能力 | 状态 |
|---|---|
| 多 Episode / 顺序处理 / Reference Clips | Implemented |
| Breakdown / ASR / OCR / Qwen3-VL | Implemented |
| Character V10.1 / Scene / Prop | Implemented |
| SourceDramaSnapshot | Implemented |
| Target Character / Scene Localization | Implemented |
| Target Dialogue / Qwen3-TTS | Implemented |
| Dialogue Timing / RemakeTimeline | Implemented |
| GenerationSegment | Implemented |
| MiniMax H3 Context / GenerationAttempt | Implemented |
| H3 structural + semantic QC / retry / selection | Implemented |
| LatentSync PostProduction | Implemented |
| Safe background audio R10.1 | Implemented |
| SRT + Episode MP4 assembly/export | Implemented |
| Repository isolated CI | Passing on current R7–R10.1/front-end lines |
| User machine real GPU/model/project acceptance | **PENDING** |

“代码已实现”不等于“你的本机模型链和真实成片已经验收通过”。当前真正的下一里程碑是拿真实短剧完成本机端到端看/听验收，而不是继续增加新的 R11 业务层。

## 正式用户界面

当前普通用户只需要理解三个区域：

```text
Project
Review Center（待确认）
Output
```

自动分析、资产解析、时间轴规划、H3 生成、QC 和后期任务都在后台执行。只有真正不确定、冲突、高风险或重复失败的问题进入 Review Center。

正式前端入口：

```text
frontend/src/views/ProjectListV4.vue
frontend/src/views/ProjectStudioV4.vue
```

## 当前主要 Runtime

| Runtime | 默认地址 | 用途 |
|---|---|---|
| Studio FastAPI | `127.0.0.1:8000` | 业务 API / SQLite / Task orchestration |
| Qwen3-VL OpenAI-compatible | 默认 `127.0.0.1:8001/v1` | 内容语义 + H3 semantic QC |
| Qwen3-TTS worker | `127.0.0.1:7861` | 目标人物音色设计/克隆/对白 |
| LatentSync 1.6 worker | `127.0.0.1:7862` | 目标说话人口型 |
| Audio Separator worker | `127.0.0.1:7863` | 安全复用原剧非对白背景 |
| MiniMax H3 FL2VA | `127.0.0.1:30010` | H3 生成 |
| MiniMax H3 Ref2VA | `127.0.0.1:30011` | Reference Video 驱动 H3 生成 |

H3、Qwen3-TTS、LatentSync、Audio Separator 使用隔离 Runtime。不要把所有模型依赖硬塞进主 `.venv`。

## 快速运行

### 1. 后端

```powershell
cd D:\ai-drama-studio
.\.venv\Scripts\Activate.ps1
python -m uvicorn engine.app.main:app --host 127.0.0.1 --port 8000
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

当前 FastAPI app version：`2.7.0`。

### 2. 前端

```powershell
cd D:\ai-drama-studio\frontend
npm install
npm run dev
```

浏览器：`http://127.0.0.1:5173`

### 3. 检查完整本地 Runtime 栈

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check_local_remake_runtime_stack.ps1
```

这个检查是只读的，不会安装或启动模型。任何 `NOT READY` 都会给出对应处理提示。

### 4. 真实项目端到端验收

只看当前状态：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_real_project_acceptance_v1.ps1 `
  -ProjectId PROJECT_你的项目ID
```

按当前缺口断点续跑：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_real_project_acceptance_v1.ps1 `
  -ProjectId PROJECT_你的项目ID `
  -Run
```

脚本只调用正式生产 API。遇到真实 ReviewIssue 会停在 `NEEDS_REVIEW`，不会自动忽略；全部机器门禁通过后也只会到 `READY_FOR_MANUAL_ACCEPTANCE`，最终仍必须人工看/听成片。

## 人物正式基线

```text
Character V10.1
runtime:  character-v10.1-capture-first-model-classification
asset:    f05-assets-v10.1-person-evidence-model-classification
resolver: person-evidence-model-classifier-v10.1
```

原则仍然是：Track 不是 Character、Face 不是身份本身、强冲突不能硬合并、无法确认的 Evidence 保持 unresolved。

## 本地数据

默认业务数据：

```text
data_v2/
├ studio_v2.sqlite3
├ models/
└ workspace/
```

可通过：

```powershell
$env:AI_DRAMA_STUDIO_HOME="D:\ai-drama-studio-data"
```

改变业务数据目录。模型权重、隔离 Runtime 和生成媒体均不应提交 Git。

## 测试

核心独立 CI 目前拆分为：

```text
r7-generation-segments
r8-h3-generation
r9-h3-qc
r10-postproduction
frontend-v2
Real Project Acceptance Orchestrator (Windows tooling)
```

本地普通代码测试不能替代真实 GPU/模型/视频验收。最终必须检查：

- 目标人物是否稳定且没有原演员泄漏；
- LOCALIZE 场景是否符合目标地区；
- 动作、构图、运镜、节奏是否满足参考意图；
- 目标语言对白是否自然且时长合理；
- 多人镜头是否同步到正确说话人；
- 是否仍残留任何原语言对白；
- 安全背景音与目标对白混音是否自然；
- 字幕和整集时间轴是否正确；
- MP4 / SRT 是否可正常播放和导出。

## Legacy

仓库保留旧 Shot、Breakdown、Character V1–V10 和历史 Feature 文档用于回归、兼容和算法参考。不要根据旧文件名推断当前正式产品状态。

当前事实优先级：

```text
docs/PROJECT_STATE.md
当前可执行代码
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
AGENTS.md / SKILL.md
历史文档
```
