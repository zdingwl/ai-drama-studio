# AI Drama Studio — Agent Entry Rules (Reference Video V2)

本仓库已经于 2026-08-24 按用户明确决策重建为 **Reference Video 驱动的短剧本地化重制工作台**。

## 1. 当前唯一产品基线

读取顺序：

```text
1. AGENTS.md
2. SKILL.md
3. docs/PROJECT_STATE.md
4. docs/REFERENCE_VIDEO_V2_ARCHITECTURE.md
5. 当前 Feature 文档（目前 F05: docs/F05_CONTENT_ANALYSIS_V2.md）
6. 当前 V2 代码 / 测试 / Session
```

旧的 35 Feature、F01-F06 Frozen Snapshot、Workflow Versioning Refactor、旧 Source Video / Shot Candidate / Final Shot 设计都属于 **Legacy History**，不能覆盖 V2 决策。

## 2. V2 核心原则

```text
Project
→ 多个 Episode（可拖动排序）
→ Preprocess
→ Shot
→ 每个 Shot 保存独立 Reference Clip
→ 人物 / 场景 / 关键道具 / Dialogue / Track / Mask 绑定 Shot
→ 替换资产 + Voice + 本地化 Dialogue
→ 按 Shot 选择重制策略
→ Reference Video 驱动视频生成
→ 弹性 Production Timeline
→ QC / Export
```

原镜头本身承担动作、构图、机位、人物空间关系、镜头运动和大部分节奏信息，因此 V2 不追求把这些信息全部转换成高成本文字描述。

## 3. 正式阶段

```text
F01 项目管理
F02 剧集导入与排序
F03 视频预处理
F04 自动拉片 / Reference Clip
F05 人物 / 场景 / 道具 / 台词智能识别
F06 拉片审核与人工修正
F07 替换素材与资产绑定
F08 翻译 / 本地化 / Voice / TTS
F09 重制任务规划
F10 Reference Video 视频重制
F11 弹性时间轴 / 整集合成
F12 质量检查
F13 导出
```

当前 V2：

```text
F01-F02 = 已实现
F03-F04 = 已实现代码 / 待 Windows 真实视频验收
F05 = V1 已实现 / 待真实短剧素材验收
F06-F13 = 尚未实现
```

不能把 Legacy 页面接回来冒充当前阶段实现。

## 4. F05 当前事实

F05 是 **AI Evidence 层**，不是 Final 数据层。

当前实现：

```text
Character Candidate / Track
  = YuNet + SFace + HOG Person + Body/Clothing Evidence
Scene Candidate
  = Thumbnail Visual Clustering
Source Dialogue
  = faster-whisper
Speaker
  = 可选本地 pyannote Pipeline
Speaker → Character
  = 保守共现映射
Key Prop
  = Evidence 表已建立，自动模型尚未配置
```

人物不能等同于人脸。未露脸但检测到人体时允许形成 `face_visible=false` 的 body-only Track；无脸证据只允许保守相邻 Shot 聚类。

F05 自动结果保存到独立 `v2_*_candidate/evidence` 表；F06 以后才写 Final Character / Scene / Prop / Dialogue，禁止覆盖原始 AI Evidence。

## 5. 数据原则

- 项目允许多个 Episode。
- `Episode.sort_order` 是所有批量任务的唯一顺序依据。
- 批量预处理、批量拉片和后续 GPU 重任务默认 **顺序执行，concurrency = 1**。
- 所有正式媒体时间使用 integer microseconds。
- Shot 是核心生产单元。
- Reference Clip 是正式资产，不是临时缓存。
- Character / Scene / Prop 是项目级实体，Shot 引用实体 ID。
- Dialogue 必须区分 `dialogue / narration / inner_monologue`；F05 可先保留 `unknown`，F06 人工确认。
- 人物识别不能只依赖人脸；Face + Body Evidence + Track 是最低基线，专用 Body ReID / Mask 可后续替换增强。
- 新语言时长不要求等于原语言时长；最终使用 Production Timeline。

## 6. V2 主代码边界

```text
engine/app/main.py
engine/app/studio_v2.py
engine/app/media_v2.py
engine/app/content_models_v2.py
engine/app/character_visual_v2.py
engine/app/content_analysis_v2.py
frontend/src/views/ProjectList.vue
frontend/src/views/ProjectStudio.vue
frontend/src/api/client.ts
frontend/src/types/studio.ts
```

旧业务模块仍可能存在作为历史代码，但不得被 V2 `main.py` / Router 重新引用，除非用户明确决定复用其中某个算法实现。

## 7. 测试基线

默认 pytest 只运行：

```text
engine/tests/v2
```

旧 `engine/tests/unit` 验证的是废弃架构，不是 V2 Release Gate。

F03-F05 除单元测试外必须在用户 Windows 本机用真实短剧素材验证；特别关注 Reference Clip、body-only Track、跨 Shot 人物聚类、Scene 聚类和 ASR 时间绑定。

## 8. Git 工作方式

用户已明确要求：**不要为日常开发新建分支，直接在默认分支 `main` 开发。**

```text
Default Branch: main
Current Development Branch: main
```

规则：
- 后续代码、文档、测试直接提交到 `main`；
- 不主动创建 feature/rebuild 分支；
- 不主动创建 PR；
- 已存在的 `rebuild/reference-video-v2` 仅作为历史分支保留，不再作为开发入口；
- 只有用户以后明确要求时，才改变这一 Git 工作方式。

## 9. 最重要的判断标准

任何新功能都先问：

> 这个数据是否是未来重制 Shot 时 Reference Video 无法可靠提供、但系统必须知道的信息？

如果 Reference Video 已经天然包含，而且结构化后没有明显编辑/绑定/生成价值，就不要为了“拉片看起来详细”而增加高成本字段。
