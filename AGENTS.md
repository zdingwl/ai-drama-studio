# AI Drama Studio — 当前开发规则

> 本文件给开发者和开发代理使用。
>
> `README.md / AGENTS.md / SKILL.md` 保留约定文件名，内容统一使用中文；正式业务文档使用中文文件名。

## 1. 先读当前正式文档

任何开发前按顺序读取：

```text
1. docs/00_短剧重做系统开发总纲.md
2. docs/01_十个模块详细设计.md
3. docs/02_工作流V2技术实现规范.md
4. docs/03_当前项目状态与验收.md
5. 当前相关代码和测试
6. 历史文档仅作算法/兼容/回归参考
```

如果旧文档和上面 00/01/02 冲突，以当前中文正式文档为准。

## 2. 产品目标

输入现有短剧，理解原片剧情、人物、动作、镜头、对白和节奏，然后根据项目目标语言、目标地区和场景策略，用本地 MiniMax H3 重新生成一部本土化短剧。

当前 10 个业务模块：

```text
1 创建项目
2 拆分原片
3 看懂原片
4 整理原片人物和场景
5 固化 SourceDramaSnapshot
6 设计目标人物/场景/声音
7 目标对白 + TTS
8 RemakeTimeline + GenerationSegment
9 H3 重拍 + QC + Selection
10 口型 + 音轨 + 字幕 + EpisodeOutput
```

正式用户工作区只有：

```text
Project
Review Center
Output
```

不要给内部算法和中间数据随意新增顶层产品页面。

## 3. 修改代码的基本原则

1. 先看现有代码、目录、模型、接口和数据库，再决定怎么改；
2. 优先最小改动，不为“架构漂亮”推翻已经可用的实现；
3. 新功能必须明确属于 10 个模块中的哪一个；
4. 输入、正式输出、下游消费者和完成条件必须明确；
5. 不把临时证据当正式业务数据；
6. 不用前端状态掩盖后端数据问题；
7. 不为了减少人工审核而降低人物身份、H3 QC、Lip Sync 等安全门槛；
8. 代码完成、CI 通过、本地模型真实运行、用户成片验收必须分开记录。

## 4. 原片事实硬规则

```text
SourceDramaSnapshot = 模块 6—10 唯一原片正式事实入口
```

必须保持：

- Source ASR / OCR / Shot truth 下游只读；
- LocalSubject / Track / Face != Final Character；
- Source Character != TargetCharacter；
- Source Scene != Target Scene；
- 完整 Dialogue Utterance 与 Shot Projection 为 1:N；
- 一条完整对白跨多个 Shot 不能变成多条独立业务对白；
- 人物/说话人/场景绑定修改后，应形成新 revision / fingerprint 并让下游失效，而不是静默修改历史结果。

Character V10.1 的身份阈值和 fail-closed 原则不得为了“让页面少几个 Review”而降低。

## 5. 目标版本和时间轴硬规则

人物始终替换/本土化。

场景策略：

```text
AUTO | KEEP | LOCALIZE
```

AUTO 最终必须固化为明确业务决定。

目标对白顺序固定：

```text
完整源对白
→ 翻译
→ 本土化
→ 最终目标台词
→ 目标说话人 / Voice
→ TTS
→ 真实语音时长
→ RemakeTimeline
→ GenerationSegment
```

禁止先猜目标语音时长再排最终时间轴。

禁止用全局不自然加速语音/慢放视频解决目标语言时长差异。

## 6. H3 硬规则

```text
Shot != GenerationSegment
GenerationAttempt != 可用镜头
GenerationSelection = 当前正式可用版本指针
```

业务代码通过 Provider：

```text
业务层
→ VideoGenerationProvider
→ MiniMaxH3Provider
→ H3RuntimeManager
→ local SGLang
```

不要从 remake 业务 Service 直接调用 SGLang。

当前 H3 生成窗口：

```text
4..15 秒
<4 秒：生成至少 4 秒后精确裁切
>15 秒：拆分多个 GenerationSegment
```

Ref2VA 的源 Reference Video 只能作为动作、表演、构图、运镜参考；源语言音轨必须去掉，目标 TTS 作为独立音频条件。

## 7. H3 QC / Retry / Selection 硬规则

GenerationAttempt 技术成功后仍需：

```text
ffprobe
→ 完整 ffmpeg decode
→ 时长硬门禁
→ Qwen3-VL 语义 QC
→ PASS / RETRY / REVIEW
```

QC 至少检查：

- 视觉结构；
- 原演员身份泄漏；
- TargetCharacter 一致性；
- 场景；
- 动作/表演；
- 构图/运镜；
- 前后 Selected Output 连续性。

安全重试必须：

- 有最大次数；
- 更换 seed；
- 加入具体 QC correction；
- 不允许无限循环。

结构失败不能人工绕过。

后期只能读取 `GenerationSelection / Selected Output`，不能读取“最近一次 SUCCEEDED Attempt”。

## 8. 后期硬规则

```text
GenerationSelection
→ PostProductionSegment
→ EpisodeOutput
```

Lip Sync：

- off-screen 对白：保留目标音频，不改嘴；
- 单一可见目标说话人：可做整段 LatentSync；
- 多脸：先做目标身份定位，再对目标 ROI 做 LatentSync；
- 身份无法安全确认：进入 LIP_SYNC_QC；
- 模型离线：WAITING_RUNTIME，不是假人工 Case。

音频：

```text
raw source audio 永远不能直接混入目标成片
```

源背景如果复用：

```text
源 Shot 音频
→ audio separator
→ SourceDramaSnapshot 对白窗口再次硬抑制
→ 映射目标时间
→ 保守混音 / duck / limiter
```

背景 Worker 失败允许安全降级到目标对白-only，不阻塞 EpisodeOutput。

## 9. 页面和 API 硬规则

打开页面、刷新、切换 Tab/Route：

```text
只读
```

绝对不能因为 mount / refresh / task finished 自动启动下一项重任务。

GET 必须：

- 不写数据库；
- 不创建任务；
- 不同步/关闭 Review Case；
- 不启动模型；
- 不隐式重算。

重任务只能由用户明确动作通过 POST command/task 创建。

服务端必须有幂等保护：

- Idempotency-Key；
- expected workflow revision；
- input fingerprint；
- processing scope。

不能只依赖前端按钮 disabled。

## 10. Workflow 状态规则

阶段至少分开：

```text
Validity  = NOT_BUILT | CURRENT | STALE
Readiness = READY | BLOCKED_REVIEW | BLOCKED_DEPENDENCY | WAITING_RUNTIME
Execution = IDLE | QUEUED | PROCESSING | SUCCEEDED | FAILED | INTERRUPTED
```

只有：

```text
Validity = CURRENT
Readiness = READY
```

才允许下游消费。

`Execution = SUCCEEDED` 不等于业务完成。

Project / Review Center / Output / Header / Task Center 必须消费同一个 `ProjectFlowState` revision，前端不要自己猜流程状态。

## 11. Review Center 规则

Review Case = 用户需要做的一次正式决定。

一个上游根问题只创建一个 Case；下游只显示被阻塞，不复制几十个待办。

用户操作必须写正式业务对象，然后运行 Validator；只有阻塞条件真正消失后才能把 Case 标记 RESOLVED。

禁止通用“忽略/已处理”绕过：

- CHARACTER_IDENTITY；
- SPEAKER；
- H3_QC；
- LIP_SYNC_QC；
- 其他硬质量门禁。

## 12. 后台任务规则

重任务应支持：

- input fingerprint；
- checkpoint；
- heartbeat；
- 有限 retry；
- cancellable（任务支持时）；
- 中断恢复；
- 已通过检查点复用；
- 清晰 last_error；
- 带时区时间字段。

任务完成只刷新 Workflow Snapshot 和通知用户，不自动创建下一项重任务。

## 13. 当前开发顺序

```text
P0 停止隐式任务 / GET 写入 / stale 误计数
P1 SourceDialogueUtterance / Projection / Person Mapping / Snapshot V2 / ReviewCase / FlowState
P2 每模块只读 Validator
P3 幂等、checkpoint、heartbeat、恢复和复用
P4 前端统一 Workflow Snapshot
P5 迁移当前测试项目并真实端到端验收
```

不要绕过 P0/P1 直接继续堆新的 H3 后续业务层。

## 14. Git 规则

```text
main = 当前开发
backup/* = 回滚恢复，不做普通开发
```

当前已有回滚点：

```text
backup/pre-r9-20260901
backup/pre-r7-20260901
backup/pre-h3-remake-restructure-2026-09-01
```

代码和文档默认修改 `main`，除非用户明确指定其他分支。

每次涉及数据契约、用户流程或完成条件的代码修改，都应同步检查 `docs/00/01/02/03` 是否需要更新。