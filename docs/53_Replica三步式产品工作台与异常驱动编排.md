# Replica 三步式产品工作台与异常驱动编排

> 日期：2026-09-13
> 状态：产品层正式整改合同与工程实现已完成；统一真实 Provider / Runtime / 人工看听验收仍待执行。本文只改变普通用户的产品编排与呈现，不删除或弱化 P5~P17 的工程合同、Artifact、ProviderJob、revision、provenance、CURRENT / STALE 与人工质量门。
> 优先级：普通用户产品流程以本文为准；`docs/20~21` 的“复杂度属于系统，不属于用户”原则扩展到完整 Replica Target / Production 链。P14~P17 的工程验收状态继续以 `docs/52` 为准。

## 1. 产品结论

Replica 普通用户主流程固定收口为三步：

```text
1. 原片
   上传完整视频
   → 解析原片
   → 查看原片剧本 / 分镜 / 人物场景道具

2. 改编设定
   生成改编方案
   → 查看目标人物 / 场景 / 道具 / 对白
   → 只在需要主观判断时确认
   → 选声线并听审目标对白
   → 系统检查对白时长

3. 生成成片
   生成视频
   → 系统内部编译正式分镜与生成分段
   → 视频生成与技术质检
   → 用户只检查真实画面质量
   → 后期 / 口型 / 正式音频 / 字幕
   → 用户播放并确认最终成片
```

普通用户不再逐阶段操作 P11 / P12 / P13 / P14 / P15 / P16 / P17，也不再面对 Candidate、Artifact、ProviderJob、SHA256、ffprobe、GenerationAttempt、TimingPlan 等工程概念。

工程诊断入口继续通过：

```text
?debug=1
```

保留全部现有细粒度工作区。

## 2. 复杂度分层

后台正式架构保持：

```text
Root Project Skill
→ ProjectExecutionPlan
→ Professional Skills
→ Provider / Runtime
→ Typed Artifacts
→ Artifact Graph
```

新增的是 Product Orchestration 层：

```text
普通用户显式动作
→ Product Pipeline Task
→ 检查 CURRENT / STALE
→ 只运行缺失或失效的内部子步骤
→ 在确定性步骤自动继续
→ 在主观质量门停下
→ 返回一个用户可理解的“下一步”
```

Product Orchestration 不是新的 Source / Target / Production Truth，也不创建替代 Artifact。它只编排已有正式 Professional Skill 与 Artifact publication。

## 3. 页面加载与显式动作

继续严格遵守：

- 页面加载 / 刷新只允许 GET；
- GET 不得创建 Task、ProviderJob、Candidate 或 Artifact；
- 任何远端 / 重模型执行必须来自用户显式 POST；
- 一个产品级显式 POST 可以授权连续执行多个确定性或低风险内部步骤；
- 该授权不能替用户做主观内容质量判断；
- 子任务继续保留独立 Task / ProviderJob / provenance / fingerprint；
- 失败 fail closed，不得把部分成功伪装成完整产品步骤完成；
- 已有 CURRENT 结果幂等复用，不能为了“流程完整”重复计费。

## 4. 第一步：原片

沿用 `docs/21` 已通过的产品模型：

```text
上传原片
→ POST /commands/source-analysis
→ P5~P10 内部编排
→ 原片剧本 / 分镜 / 人物场景道具
```

P5~P10 不重新暴露为用户阶段。

## 5. 第二步：改编设定

新增产品级“生成改编方案”命令。一次显式操作内部允许：

```text
CURRENT SOURCE_VIDEO_SNAPSHOT
→ P11 Target Bible
→ P12 Target Script
→ P13 Target Assets candidate
```

规则：

- P11 / P12 已是正式可用能力，可以在同一显式产品命令内顺序执行；
- P13 仍保留真实主观审核门，Product Pipeline 到候选后必须停下；
- 普通用户只看到一个“改编方案待确认”，不需要理解 P11/P12/P13；
- 确认页以人物、场景、关键道具、最终对白与目标地区整体方向为中心；
- 正式 `TARGET_ASSETS` publication 仍通过现有 optimistic-concurrency review command；
- Reject 后仍保留旧 CURRENT，不覆盖历史正式结果。

## 6. 配音与对白时长：只在需要时打断

P14 继续保留工程合同，但普通产品界面改成：

```text
选择角色声线
→ 生成配音
→ 播放听审
→ 确认配音
→ 系统检查对白时长
```

普通模式不显示 P14 / Timing / ffprobe / duration factor 等术语。

时长检查结果：

- 全部可放入原片节奏：直接显示“对白时长已匹配”；
- 少量可通过受控重录改善：只展示受影响对白和“重新录这一句”；
- 明显过长必须改写：只展示受影响对白和“缩短这句对白”；
- 不允许一键盲目把全部对白拉到 0.8；
- 任何重录仍需真实媒体落盘、SHA256、ffprobe，再重新计算 Timing；
- Target Script 定向修订后旧 Audio / Timing 按既有 Artifact Graph 规则 STALE。

声线库的元数据管理、完整筛选、逐句表演参数、P14 技术验收检查全部移入 `?debug=1`；普通用户只看到角色、声线试听、选择和必要异常处理。

## 7. 第三步：生成成片

新增产品级“生成视频”命令。前置必须是：

```text
CURRENT TARGET_ASSETS
CURRENT TARGET_SCRIPT
CURRENT TARGET_AUDIO
CURRENT TIMING_PLAN
```

用户一次显式点击后内部允许：

```text
P15 deterministic Replica compile
→ P15 candidate
→ 在本次用户“生成视频”授权范围内确定性 publication
→ P16 MiniMax H3 generation + technical QC
→ P16 video candidate
→ STOP：等待用户真实看画面
```

P15 不再作为普通用户独立确认阶段，因为它只按已确认上游与 Source Shot / Timing 做 deterministic compile，不重新进行主观故事创作。其 publication provenance 必须明确来自本次用户产品命令授权，不能伪造为单独人工逐镜审核。

P16 必须继续停在真实画面质量门：

- 系统技术 QC 只能证明媒体技术可用；
- 人物一致性、场景、动作、构图、连续性、明显生成崩坏仍由用户观看决定；
- 普通用户只看到“检查生成视频”，不显示 GenerationAttempt / Technical QC 表格；
- Reject 后重新生成，不让失败 attempt 进入正式 Selection。

## 8. 最终成片

P16 正式选片后，普通用户点击“制作最终成片”：

```text
CURRENT GENERATION_SELECTION
→ P17 conditional Lip Sync
→ trim / concatenate
→ formal Target Audio
→ SRT
→ final candidate
→ STOP：等待用户播放最终 Episode
```

只有用户播放检查并显式确认后才发布 `FINAL_OUTPUT`。

## 9. 普通用户只看到一个下一动作

产品状态聚合 GET 必须把工程状态压缩为以下用户动作之一：

```text
UPLOAD_SOURCE
ANALYZE_SOURCE
GENERATE_ADAPTATION
REVIEW_ADAPTATION
CAST_VOICES
REVIEW_AUDIO
FIX_DIALOGUE_DURATION
GENERATE_VIDEO
REVIEW_VIDEO
BUILD_FINAL
REVIEW_FINAL
COMPLETE
```

页面主区只突出当前动作。已完成步骤折叠成摘要，未来步骤只显示“等待前一步”，不堆操作按钮。

## 10. Debug 模式

`?debug=1` 继续展示现有细粒度工程工作区，包括：

```text
Target Bible
Target Script
Target Assets candidate / review
P14 Voice Catalog / Audio / Timing
Timing Overflow Triage
逐句 Retake
P14 Acceptance Readiness
P15 Storyboard candidate
P16 GenerationAttempt / QC / Selection
P17 Post candidate / FINAL_OUTPUT
```

普通产品模式禁止出现 P 编号、Artifact id、fingerprint、ProviderJob、Candidate sequence、SHA256、ffprobe 等工程语言。

## 11. 验收与 Capability 状态

本次是产品层整改，不是 P14~P17 最终真实验收。

完成本轮代码后仍必须保持：

```text
P14 PASS = NO
P15 PASS = NO
P16 PASS = NO
P17 PASS = NO

TTS = PLANNED
TIMING = PLANNED
STORYBOARD = PLANNED
VIDEO_GENERATION = PLANNED
QC_SELECTION = PLANNED
LIP_SYNC = PLANNED
POST_PRODUCTION = PLANNED
```

最终真实验收应改为从普通用户三步工作台完整走一遍，而不是要求用户逐个工程面板验收。

## 12. 当前工程实现与自动验证

本轮已落地 Product Orchestration，而不是只隐藏旧面板：

```text
GET  /projects/{project_id}/replica-workflow
POST /projects/{project_id}/commands/replica-adaptation
POST /projects/{project_id}/commands/replica-generation
POST /projects/{project_id}/commands/replica-final-output
```

实现规则：

- `replica-workflow` 只读聚合 CURRENT Artifact、待审核候选与活动 Task，返回一个 `next_action`；
- `replica-adaptation` 复用现有 P11 → P12 → P13 子任务，并在 P13 主观视觉审核门停止；
- `replica-generation` 在六个正式 CURRENT 输入齐全后运行 P15 → P16；P15 deterministic candidate 只在本次用户显式“生成视频”授权范围内 publication，P16 仍停在真实画面人工审核门；
- `replica-final-output` 复用 P17 后期任务，并在最终成片人工播放确认前停止；
- P14 配音、Timing、Retake、P12 Timing Rewrite 的正式工程路径继续复用，普通产品层只把它们翻译为“选声线 / 试听配音 / 检查对白节奏 / 处理少量过长对白”；
- Reject 后的新一轮生成把候选 generation sequence 纳入 Product Task fingerprint，避免旧 succeeded Product Task 错误吞掉用户的新请求；
- 普通 `App.vue` 只挂载 Source Workspace + Replica 三步工作台；原 P11~P17 细粒度组件全部进入 `?debug=1`。

本轮实际自动验证：

```text
Replica Product backend focused tests = PASS
P12 / P14 / P15~P17 + Product focused regression = 20 / 20 PASS
frontend product workspace + App tests = 4 / 4 PASS
frontend full Vitest = 102 / 102 PASS
frontend vue-tsc + production build = PASS
backend full pytest = PASS (exit code 0)
```

这些结果证明产品编排与既有工程合同未发生自动测试回归；它们仍不能替代 P14~P17 的真实 Provider / Runtime、真实素材端到端和用户最终看听质量验收。
