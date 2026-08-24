# AI Drama Studio — Agent Entry Rules (Reference Video V2)

本仓库已经于 2026-08-24 按用户明确决策重建为 **Reference Video 驱动的短剧本地化重制工作台**。

## 1. 当前唯一产品基线

读取顺序：

```text
1. AGENTS.md
2. SKILL.md
3. docs/PROJECT_STATE.md
4. docs/REFERENCE_VIDEO_V2_ARCHITECTURE.md
5. 当前正在开发的 V2 代码 / 测试
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

当前代码基线只把 F01-F04 实现为可操作功能；F05-F13 只能在其真实业务实现完成后标记可用，不允许把旧页面接回来冒充实现。

## 4. 数据原则

- 项目允许多个 Episode。
- `Episode.sort_order` 是所有批量任务的唯一顺序依据。
- 批量预处理、批量拉片和后续 GPU 重任务默认 **顺序执行，concurrency = 1**。
- 所有正式媒体时间使用 integer microseconds。
- Shot 是核心生产单元。
- Reference Clip 是正式资产，不是临时缓存。
- Character / Scene / Prop 是项目级实体，Shot 引用实体 ID。
- Dialogue 必须区分 `dialogue / narration / inner_monologue`。
- 人物识别不能只依赖人脸；后续需要 Face + Body ReID + Track，Mask 作为高价值能力。
- 新语言时长不要求等于原语言时长；最终使用 Production Timeline。

## 5. 代码边界

V2 主入口：

```text
engine/app/main.py
engine/app/studio_v2.py
engine/app/media_v2.py
frontend/src/views/ProjectList.vue
frontend/src/views/ProjectStudio.vue
frontend/src/api/client.ts
frontend/src/types/studio.ts
```

旧业务模块仍可能暂时存在于仓库中作为历史代码，但不得被 V2 `main.py` / Router 重新引用，除非用户明确决定复用其中某个算法实现。

## 6. 测试基线

默认 pytest 只运行：

```text
engine/tests/v2
```

旧 `engine/tests/unit` 验证的是废弃架构，不是 V2 Release Gate。

开发 F04 及以后真实媒体能力时，除单元测试外必须在用户本机用真实短剧素材验证。

## 7. Git

`main` 仍是正式发布基线。

当前重建开发分支：

```text
rebuild/reference-video-v2
```

未经用户要求，不创建 PR、不合并到 main、不删除分支。

## 8. 最重要的判断标准

任何新功能都先问：

> 这个数据是否是未来重制 Shot 时 Reference Video 无法可靠提供、但系统必须知道的信息？

如果 Reference Video 已经天然包含，而且结构化后没有明显编辑/绑定/生成价值，就不要为了“拉片看起来详细”而增加高成本字段。
