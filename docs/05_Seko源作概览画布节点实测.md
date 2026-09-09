# Seko 3.0「源作概览分析」与逐镜拉片实测

> 更新时间：2026-09-09  
> 证据等级：B — 项目使用者提供的可复核产品实测截图与对应文本。  
> 用途：约束 AI Drama Studio V3 Source Understanding / SOURCE_BIBLE / P8 分镜表的产品设计。  
> 边界：只记录外部可观察产品行为，不声称知道 Seko 私有内部 Prompt、模型或工具编排。

---

# 1. 源作概览分析的可观察链路

实测可确认：

```text
完整短剧视频
↓
Agent 调用多模态分析
↓
返回素材基线 / 整体分析 / 时间化剧本 / 角色 / 场景 / 道具
↓
用户确认 / 微调
↓
调用文本节点创建
↓
画布生成《源作概览分析》
↓
后续调用读取节点详情
↓
继续下一项分析
```

产品层可确认：

> 原片多模态理解结果会被物化为持久、可继续读取的业务节点，而不是只停留在聊天回复里。

不能据此确认 Seko 的数据库表、Artifact 类型或内部上下文注入实现。

---

# 2. 《源作概览分析》可观察结构

实测内容主要包括：

```text
1. 素材基线
2. 整体分析
3. 时间化原剧本 / 剧情
4. 角色 / 人物关系
5. 场景
6. 关键道具
```

## 2.1 素材基线

可观察：

- 有效内容时间；
- 总时长；
- 画幅 / 帧率 / 时间基准；
- 黑边 / 裁切 / 分屏；
- 速度变化 / 快剪描述。

## 2.2 整体分析

可观察：

- 故事背景；
- 类型；
- 世界规则；
- 叙事结构；
- 人物关系；
- 视听风格；
- 节奏。

V3 不能照搬“世界规则”字段做社会泛化；当前 Grounding v2 已限制为本片内部 FACT。

## 2.3 时间化原剧本

实测节点从 00:00 到约 01:06 以剧情语义窗口组织：

```text
时间窗口
+ 画面描述
+ 对白 / 旁白
```

时间窗口可以跨多个 Shot，也可能存在语义重叠，因此不能当作 Shot Boundary。

## 2.4 角色 / 场景 / 道具

角色可观察字段：名称、剧情功能、基准外观、状态。

场景可观察字段：场景名称、时间范围、空间关系、环境细节。

道具可观察字段：名称、时间范围、外观 / 状态、剧情功能或使用方式。

---

# 3. V3 SOURCE_BIBLE 的对应语义

V3 正式定义：

```text
SOURCE_BIBLE《源作概览分析》
= 用户可读
= 可编辑
= 可版本化
= 有 provenance
= 有 CURRENT / STALE
```

它不等于：

```text
ASR raw output
OCR raw output
SHOT_ANCHORS
Provider 原始 response
聊天消息
```

正式关系：

```text
SOURCE_VIDEO
├─ derives → SHOT_ANCHORS
├─ derives → SOURCE_DIALOGUE / OCR Evidence
└─ + Evidence → SOURCE_BIBLE
```

Source Evidence 与 Source Understanding 必须分离；SOURCE_BIBLE 的编辑 / 合规表达不能反向覆盖 canonical ASR / OCR。

---

# 4. Canvas 与 Artifact Graph

Seko 可观察产品行为：

```text
生成业务结果
↓
写入画布节点
↓
用户查看 / 修改
↓
Agent 再读取节点
↓
后续 Skill 继续工作
```

V3 吸收该体验，但正式真相仍是：

```text
Artifact Graph / SourceBibleRevision
= 业务真相

Canvas / 页面节点
= 可视化与编辑入口
```

未来 Canvas 节点应引用 Artifact ID / revision，而不是把脱离 Artifact Graph 的 Markdown 当唯一真相。

---

# 5. P7 最终产品输出契约

P7 完成后，用户必须能直接读到《源作概览分析》，而不是只看到“模型成功”。

当前 V3 已实现并真实验收：

```text
素材基线
整体分析
时间化原作剧情
人物 / 关系
场景
关键道具
Story / 关键事件
Story Skeleton
Rhythm Skeleton
revision / provenance
```

并满足：

- revision / fingerprint；
- CURRENT / STALE；
- 完整 Episode + Source Evidence provenance；
- 用户可编辑且编辑生成新 revision；
- 下游依赖正确 STALE；
- GET 只读；
- Evidence 可追溯但默认不淹没主文档；
- Source Evidence 原文不被 SOURCE_BIBLE 改写。

P7 最终验收见 `docs/07_P7最终验收与ProviderReadiness.md`。

---

# 6. 新增实测：源作概览之后直接进入逐镜拉片

项目使用者继续实测后观察到：

```text
《源作概览分析》
↓
读取节点详情
↓
逐镜拉片分析
↓
调用「分镜表」工具
↓
生成完整逐镜表
```

这进一步确认产品层存在两个不同业务结果：

```text
整集 Source Understanding
!=
逐镜 Shot Breakdown
```

因此 V3 保持：

```text
P7 = SOURCE_BIBLE / Story / Rhythm
P8 = 逐镜精细拉片 / 分镜表
```

不能为了接近 Seko 外观而把 P7/P8 数据职责合并。

---

# 7. Seko 分镜表可观察列

实测分镜表每行对应一个源镜头，页面可观察列包括：

```text
镜头编号
源片段
时长
画面描述
镜头语言
绑定主体
对白 / 旁白
音效
```

其中“镜头语言”内部可观察到：

```text
景别
构图
镜头类型 / 角度
运镜方法
焦距 / 景深
```

“绑定主体”可观察到：

```text
角色
场景
道具
```

源片段以可播放缩略视频 / Reference Clip 方式展示。

---

# 8. 对 P8 的直接约束

P8 正确输入：

```text
完整 Episode
+
CURRENT SOURCE_BIBLE
+
CURRENT SHOT_ANCHORS
+
需要时读取 CURRENT Source Evidence
↓
逐镜精细拉片
```

P8 不能：

```text
Shot 1 独立猜整集
Shot 2 独立猜整集
...
→ 再拼剧情
```

V3 相比外部产品观察还必须额外坚持：

- Shot start / end 优先使用 P5 SHOT_ANCHORS；
- Reference Clip 只用于局部精看，不替代完整 Episode；
- 对白正文来自 P6 canonical Evidence，P8 只做 Shot binding，不重新听写覆盖；
- 人物 / 场景 / 道具绑定必须继承 CURRENT SOURCE_BIBLE 的全局知识；
- P8 输出必须有 typed schema / revision / fingerprint / provenance / CURRENT / STALE。

---

# 9. 当前开发边界

当前 `main` 已完成：

```text
P5 Shot Anchors ✅
P6 Source Evidence ✅
P7 SOURCE_BIBLE / Story / Rhythm ✅
```

当前尚未实现：

```text
P8 逐镜精细拉片
SHOT_BREAKDOWN capability
最终逐镜分镜表 Artifact / domain schema
```

下一聊天可以正式开始 P8，但必须先重新读取当前 `main`、`AGENTS.md` 与 `docs/00~07`。
