# AI Drama Studio

本仓库用于开发一个 **本地自用的 AI 短剧重制生产工作台**。

目标不是做 SaaS，也不是做通用视频生成平台，而是把一部现有短剧转换为可编辑、可追踪、可逐镜头重制的结构化生产工程，并严格按照真实生产流程推进：

```text
上传短剧
→ 视频预处理
→ 自动拉片
→ 人工修正 Shot
→ 自动识别人
→ 人工修正人物
→ 自动识别对白
→ Speaker / Character 匹配
→ 人工修正对白
→ 自动识别 Scene
→ 人工修正 Scene
→ 本土演员库
→ AI 本土选角
→ 人工选演员
→ Character Bible
→ 人工确认
→ Scene Bible
→ 人工确认
→ Shot Specification
→ 人工确认
→ 单 Shot 视频生成
→ Generation 版本管理
→ Auto QC
→ 失败 Shot 人工处理
→ 批量生成
→ TTS
→ Dialogue Fit
→ Lip Sync
→ 最终合成
→ 整集 QC
→ 导出
```

## 最重要的开发规则

**不要按大模块并行开发。**

必须按照真实使用流程，一个 Feature 一个 Feature 纵向开发：

```text
开发当前 Feature
→ 单功能测试
→ 使用真实短剧测试
→ 人工验收
→ 修复当前 Feature
→ 再测试
→ 冻结 Input / Output / API / DB Contract
→ 才允许进入下一个 Feature
```

已经验收为 Stable 的上游 Feature，后续功能原则上只能读取其已冻结 Contract，不能为了下游开发方便而反复修改上游代码。

## 当前开发环境

- 使用方式：本地自用、单用户
- 主要系统：Windows
- 当前 GPU：NVIDIA RTX 4060 Ti 16GB
- 开发阶段目标：先保证功能完整可用，不追求速度和并发
- 前端：Vue 3 + TypeScript + Vite + Pinia
- 后端 / AI Engine：Python 3.11 + FastAPI + PyTorch + CUDA
- 视频处理：FFmpeg / FFprobe + OpenCV
- 数据库：SQLite + SQLAlchemy + Alembic
- 文件：本地 Workspace
- 桌面打包：核心流程稳定后再接 Electron
- 强 VLM / 视频生成 / 高质量 TTS / 高质量 Lip Sync：优先 API

## 核心设计原则

1. **Shot 是核心生产单元。** 单 Shot 必须可以独立分析、生成、QC、重试和人工替换。
2. **AI 原始结果与人工 Final 结果分离。** 人工修正不能覆盖 AI 原始结果。
3. **所有生成结果版本化。** Video / TTS / Lip Sync 禁止覆盖旧版本。
4. **模型必须可替换。** 业务层只认识统一 Contract，不允许绑定具体 Provider。
5. **媒体文件不进入 SQLite。** 数据库存 ID、状态、结构化 JSON 和相对路径。
6. **RTX 4060 Ti 16GB 不作为开发阻塞条件。** GPU 任务默认单并发，模型按需加载，用完释放。
7. **第一版不做 SaaS 重架构。** 不提前引入多租户、Kubernetes、复杂微服务、在线计费、GPU 集群。

## 文档入口

- [`SKILL.md`](./SKILL.md)：项目开发总技能手册，所有开发代理与工程师优先阅读。
- [`docs/FEATURE_SEQUENCE.md`](./docs/FEATURE_SEQUENCE.md)：固定的 30 个 Feature 开发顺序与 Gate。
- [`docs/TECH_STACK.md`](./docs/TECH_STACK.md)：技术栈、运行环境、AI 模型接入原则。
- [`docs/DATA_AND_FREEZE_RULES.md`](./docs/DATA_AND_FREEZE_RULES.md)：数据 Contract、版本、冻结和兼容规则。
- [`templates/FEATURE_SPEC_TEMPLATE.md`](./templates/FEATURE_SPEC_TEMPLATE.md)：每个 Feature 开发前必须填写的统一规格模板。

## 对 AI / Codex 的使用规则

任何 AI 开发代理开始实现一个 Feature 前，都必须：

1. 阅读 `SKILL.md`。
2. 确认当前应该开发的 Feature 编号。
3. 确认它依赖的上游 Feature 已经 Stable。
4. 复制 `templates/FEATURE_SPEC_TEMPLATE.md` 建立当前 Feature Contract。
5. 不修改未被当前 Feature 明确授权修改的 Stable 数据结构与代码。
6. 完成后必须给出真实素材验收项与 Freeze 清单。

如果当前 Feature 尚未通过人工验收，不得擅自继续开发下一个依赖它的 Feature。
