# P3 Result-first 拉片结果 UI

> Date: 2026-08-28
> Status: IMPLEMENTED ON `main` / browser acceptance pending

## 用户反馈

用户在本机浏览器验收 `02 拉片` 时明确指出：当前 Structured Draft 页面暴露了过多内部技术信息，例如 Run / Revision、ASR/OCR/VLM/Fusion 状态、pipeline/schema、置信度、Evidence provenance、source id / source uri 等。正常使用时这些信息难以理解，也会遮蔽真正需要的拉片结果。

用户确认的产品方向：

> 页面围绕“AI 分析出了什么”设计，而不是围绕“AI 是怎么分析的”设计。

## 本次 UI 决策

`02 拉片` 对用户只保留两个直接工作区：

```text
镜头管理
→ 检查切镜 / 拆分 / 合并 / Reference Clip

拉片结果
→ 场景 / 镜头 / 人物 / 对白 / 动作 / 关键道具 / 画面文字 / 声音 / 镜头语言 / 原镜头
```

可读结果优先。技术中间层继续作为后端事实保存，但不再默认暴露给普通用户。

## 当前实现

新增：

```text
frontend/src/components/BreakdownResultsV1.vue
```

当前结果页布局：

```text
左：镜头目录
    Scene → Shot
    历史结果折叠

中：当前镜头直接结果
    画面
    场景
    人物
    对白
    动作
    关键道具
    画面文字（有才显示）
    声音（有才显示）
    镜头作用（有才显示）
    景别 / 运镜

右：原镜头 Reference Clip
    原片时间
    上一镜 / 下一镜
```

同步调整：

```text
frontend/src/components/BreakdownStageV1.vue
frontend/src/components/BreakdownTaskBarV1.vue
frontend/src/views/ProjectStudioV3.vue
```

可见命名从：

```text
镜头边界 / 结构化草稿
```

调整为：

```text
镜头管理 / 拉片结果
```

## 默认隐藏的内部信息

正常结果页不再展示：

```text
R3 / ShotRevision 编号
pipeline_profile
schema_version
ASR / OCR / VLM / Fusion 状态条
AI confidence 数字
Evidence provenance
Evidence source_id
Evidence source_uri / file path
词级 ASR Evidence 列表
raw warnings
```

历史 Run 仍可读取，但只折叠成“历史结果”，不再向用户展示内部 pipeline / schema / revision 细节。

## 保留的工程边界

这次只重做消费层 UI，没有删除或改变 P1/P2 持久化事实：

```text
BreakdownRun
ShotRevision anchoring
SceneSegmentDraft
ShotSemanticDraft
LocalSubject / ShotLocalSubject
TimelineEvent
DraftPropHint / DraftPropOccurrence
BreakdownEvidenceLink
raw sidecars
```

Evidence / Revision / Provider 信息仍然存在，可供后续算法、调试、验收和资产阶段使用。

匿名人物语义边界不变：

```text
LocalSubject / 人物A != Final Character
```

结果页只保留一条弱提示，说明人物名称是拉片阶段临时标记，后续资产识别会回填正式人物。

## 相关代码提交

```text
b57d94b8  feat(ui): add result-first breakdown viewer
15b09718  refactor(ui): make breakdown workspace result-first
ef96379a  refactor(ui): simplify breakdown controls
4f5a6088  chore(ui): rename breakdown stage to results
```

## 验收状态

```text
implementation on main = DONE
browser/local UI acceptance = PENDING USER REVIEW
P3 fully accepted/closed = NO
```

不要因为本次 UI 重做已经落地就把 P3 标记为 CLOSED；仍需用户本机浏览器查看真实 Breakdown 数据后的明确验收。

## CI 说明

本次代码 push 已触发 `Reference Video V2 CI`。Frontend job 在进入项目类型检查之前，被仓库已有的 `vue-tsc` / TypeScript 7 compatibility 问题阻断：

```text
ERR_PACKAGE_PATH_NOT_EXPORTED
Package subpath './lib/tsc' is not defined by exports in typescript/package.json
```

因此该 CI failure 不能作为本次 Vue 页面代码通过或失败的判断。浏览器本机验收仍是当前 UI gate。
