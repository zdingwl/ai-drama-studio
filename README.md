# AI Drama Studio — 短剧本土化重做系统

AI Drama Studio 的目标很明确：

> **输入一部已经拍好的短剧，系统先理解原片，再按照目标语言、目标地区和场景策略，用本地 MiniMax H3 重新生成一部本土化短剧。**

它不是单纯的翻译/配音工具，也不是只输出拉片报告的视频分析平台。

## 先读哪份文档

后续产品和开发统一按以下顺序理解：

```text
docs/00_短剧重做系统开发总纲.md
    ↓
docs/01_十个模块详细设计.md
    ↓
docs/02_工作流V2技术实现规范.md
    ↓
docs/03_当前项目状态与验收.md
```

历史文档说明：

```text
docs/99_历史文档说明.md
```

新开发者/开发代理再读：

```text
AGENTS.md
SKILL.md
```

## 整个系统只需要记住 10 步

```text
1. 创建项目
2. 拆分原片
3. 看懂原片
4. 整理原片人物和场景
5. 固化原片事实 SourceDramaSnapshot
6. 设计目标人物、场景和声音
7. 翻译/本土化对白并生成目标语音
8. 根据真实语音时长重排时间并生成 H3 计划
9. MiniMax H3 重拍 + QC + 重试 + 选版
10. 口型 + 目标音轨 + 字幕 + 背景音 + 整集成片 + 人工验收
```

详细输入、输出和完成条件看 `docs/01_十个模块详细设计.md`。

## 普通用户只有 3 个正式工作区

```text
Project       原片准备、目标设计、对白声音、生成准备
Review Center 只处理系统无法安全决定的问题
Output        H3 重拍、质检、后期、成片和交付
```

ASR、OCR、VLM、Tracking、GenerationSegment、H3 Context、QC、Lip Sync、Audio Separation 等属于内部能力或高级诊断，不应该各自变成顶层产品页面。

## 不能破坏的核心规则

- SourceDramaSnapshot 是目标版本和生成流程唯一的原片正式事实入口；
- LocalSubject / Track / Face 不等于 Final Character；
- 人物始终替换，场景按 `AUTO / KEEP / LOCALIZE` 决定；
- 一条完整对白可以跨多个 Shot，但不能复制成多条独立业务对白；
- 必须先得到目标 TTS 的真实说话时长，再计算 RemakeTimeline；
- `Shot != GenerationSegment`；
- `GenerationAttempt != 可用镜头`；
- 只有 `GenerationSelection / Selected Output` 可以进入后期；
- 多脸口型必须先确认目标说话人身份；
- 原片原始音轨不能直接混入目标成片；
- 页面打开、刷新、切换只能读取状态，不能偷偷启动重任务；
- GET 接口不能修改业务数据；
- 模型离线属于 Runtime 问题，不是假人工审核问题；
- 代码实现、模型真实可用、真实项目跑通、用户最终验收是四件不同的事。

## 当前主要 Runtime

| Runtime | 默认地址 | 用途 |
|---|---|---|
| Studio FastAPI | `127.0.0.1:8000` | 业务 API / SQLite / Task 编排 |
| Qwen3-VL | `127.0.0.1:8001/v1` | 原片语义理解 + H3 语义 QC |
| Qwen3-TTS worker | `127.0.0.1:7861` | 目标人物声音和对白 |
| LatentSync worker | `127.0.0.1:7862` | 目标说话人口型 |
| Audio Separator worker | `127.0.0.1:7863` | 安全分离非对白背景 |
| MiniMax H3 FL2VA | `127.0.0.1:30010` | H3 生成 |
| MiniMax H3 Ref2VA | `127.0.0.1:30011` | Reference Video 驱动生成 |

重模型 Runtime 保持隔离，不要把所有模型依赖塞进主 `.venv`。

## 快速运行

后端：

```powershell
cd D:\ai-drama-studio
.\.venv\Scripts\Activate.ps1
python -m uvicorn engine.app.main:app --host 127.0.0.1 --port 8000
```

前端：

```powershell
cd D:\ai-drama-studio\frontend
npm install
npm run dev
```

浏览器：

```text
http://127.0.0.1:5173
```

本地 Runtime 只读检查：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check_local_remake_runtime_stack.ps1
```

真实项目验收：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_real_project_acceptance_v1.ps1 `
  -ProjectId PROJECT_你的项目ID
```

断点续跑：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_real_project_acceptance_v1.ps1 `
  -ProjectId PROJECT_你的项目ID `
  -Run
```

## 当前开发重点

当前不是继续增加新的“R11/R12 功能层”，而是按照 Workflow V2 先把现有代码收口：

```text
P0 停止页面隐式启动任务和 GET 写入
→ P1 收口完整对白 / Shot 投影 / 人物映射 / Snapshot V2
→ P2 只读 Validator
→ P3 幂等、检查点、可恢复任务编排
→ P4 前端统一 Workflow Snapshot
→ P5 迁移当前真实测试项目并完成本地端到端验收
```

当前真实状态、测试项目基线和验收清单以：

`docs/03_当前项目状态与验收.md`

为准。

## 历史资料

仓库保留旧 Breakdown、Character、Feature、性能和验收文档用于回归和兼容。

**旧文件名或旧阶段号不能覆盖当前 00/01/02/03 文档。**

详细规则看 `docs/99_历史文档说明.md`。