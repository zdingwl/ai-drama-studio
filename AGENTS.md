# AI Drama Studio V3 — 开发规则

## 1. 开发前读取顺序

任何代码修改前必须按顺序读取：

1. `docs/00_V3产品与系统详细规划.md`
2. `docs/01_V3开发阶段与验收清单.md`
3. 当前相关代码与测试

历史分支只能做参考，不能覆盖 V3 正式规划。

## 2. 产品边界

V3 只围绕六类项目建设：

```text
REPLICA              复刻
REDRAW               重绘
TRANSLATION          翻译
NOVEL_TO_DRAMA       小说生成短剧
SCRIPT_TO_DRAMA      剧本生成短剧
SCRIPT_LOCALIZATION  剧本本土化
```

`project_type` 必须是真实后端字段和工作流输入，禁止只在前端做六个入口但后端仍走同一条旧流程。

## 3. 统一原则

- 默认自动完成；只在系统无法安全决定或结构失败时要求人工处理。
- 普通用户只看业务结果，不展示 ASR/OCR/VLM/Tracking/Fingerprint 等内部证据细节。
- 页面 GET 必须只读，重任务必须由明确 POST/Command 启动。
- Source 与 Target 严格分离。
- Source Shot、Target Storyboard Shot、GenerationSegment 严格分离。
- GenerationAttempt 不是正式可用结果；只有 GenerationSelection 可进入后期。
- 外部付费 Provider 在远程调用前必须先持久化本地 Job，禁止把密钥写入数据库、日志、Artifact 或 Git。
- 批量 Episode 默认按顺序串行处理，不因批量上传而默认并行跑重模型。

## 4. 视频类项目的原片理解顺序

正式业务顺序必须是：

```text
导入原片
→ 媒体检查
→ Shot Boundary（只做时间锚点）
→ ASR + OCR
→ 整集理解
→ Source Bible
→ 带 Source Bible 做逐镜精细拉片
→ 人物/场景/道具/Speaker 归一
→ SourceVideoSnapshot
```

禁止退回“先逐镜猜完整剧情，最后再拼成整集理解”的旧顺序。

## 5. 下游统一生产边界

不同来源最终都必须汇入统一目标生产层：

```text
Source Snapshot / Source Text Facts
→ Adaptation Plan
→ Target Bible
→ Target Script
→ Target Storyboard
→ Voice/TTS
→ Timing Plan
→ GenerationSegment
→ MiniMax H3
→ QC / Retry / Selection
→ Lip Sync / Audio / Subtitle / Edit
→ Final Output
```

六类项目可以跳过不需要的阶段，但不能伪造已完成阶段。

## 6. 技术原则

首版技术栈继续优先：

- Backend: Python + FastAPI + Pydantic + SQLAlchemy + Alembic + pytest
- Frontend: Vue 3 + TypeScript + Pinia + Vue Router + Vite + Vitest
- Media: FFmpeg / ffprobe
- ASR: faster-whisper
- OCR: RapidOCR 或可替换 Provider
- 整集音视频理解：`SourceEpisodeUnderstandingProvider`，默认中国大陆可稳定调用的 Provider
- 逐镜视觉理解：`SourceShotUnderstandingProvider`，默认 Qwen3.8 系列
- Speaker：可替换 Audio-Visual Speaker Provider
- TTS：Qwen3-TTS Provider
- Video Generation：`VideoGenerationProvider -> MiniMaxH3Provider -> local runtime`
- Lip Sync：LatentSync Provider

模型名可以替换，业务数据契约不能绑死到模型名。

## 7. 状态与任务

每个重阶段至少记录：

```text
Validity: NOT_BUILT | CURRENT | STALE
Readiness: READY | BLOCKED_DEPENDENCY | WAITING_RUNTIME | BLOCKED_TECHNICAL | NEEDS_USER_DECISION
Execution: IDLE | QUEUED | PROCESSING | SUCCEEDED | FAILED | INTERRUPTED
```

只有 `CURRENT + READY` 的正式产物可以被下游消费。

任务必须逐步支持 input fingerprint、幂等、checkpoint、heartbeat、有限 retry、cancel/resume。

## 8. Git 规则

```text
main = V3 当前开发
backup/* = 历史回滚/参考
```

禁止 force push。

重大结构变化先更新规划，再编码。
