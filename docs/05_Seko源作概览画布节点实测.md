# Seko 3.0「源作概览分析」画布节点实测

> 日期：2026-09-08  
> 证据等级：B — 项目使用者提供的可复核产品实测截图与对应文本内容。  
> 用途：补充 `docs/03_Seko3.0_Skill架构逆向分析.md`，用于约束 AI Drama Studio V3 的 Source Understanding / Canvas / Artifact 设计。  
> 边界：本文只记录外部可观察产品行为，不声称知道 Seko 私有内部实现、Prompt、模型或工具编排细节。

---

# 1. 本次新增实测行为

此前已经观察到：

```text
完整短剧视频写入画布
→ Agent 调用「多模态分析」
→ 返回素材基线 / 整体分析 / 时间化剧本 / 角色 / 场景 / 道具
→ 建议写入画布
```

本次继续操作：

```text
点击「合规微调后重新写入画布」
↓
界面显示调用工具「文本节点创建」
↓
画布实际出现文本节点《源作概览分析》
↓
界面继续显示调用工具「读取节点详情」
↓
Agent 继续基于该节点推进后续工作
```

这说明在产品层可以确认：

> **原片多模态理解结果不仅存在于聊天回复里，还会被物化成画布中的持久文本节点，并可以被 Agent 再次读取。**

不能据此确认 Seko 的数据库表、Artifact 类型、节点存储格式或内部上下文注入方式。

---

# 2. 《源作概览分析》节点实际内容结构

项目使用者导出的节点文本包含四个主块：

```text
1. 素材基线
2. 整体分析
3. 完整原剧本
4. 完整角色、场景和关键道具列表
```

## 2.1 素材基线

可观察字段包括：

- 有效内容起止时间；
- 总时长；
- 画幅；
- 有效画面；
- 帧率 / 时间基准；
- 黑边 / 裁切 / 分屏；
- 速度变化 / 快速剪辑描述。

## 2.2 整体分析

可观察内容包括：

- 故事背景；
- 类型；
- 世界规则；
- 叙事结构；
- 人物关系；
- 视听风格；
- 节奏。

## 2.3 完整原剧本

节点包含从 `00:00` 到约 `01:06` 的时间化剧本，逐段组合：

```text
时间窗口
+ 画面描述
+ 对白 / 旁白
```

这些时间窗口存在重叠，因此它们属于语义 / 剧情时间窗口，不能当作精确 Shot Boundary。

## 2.4 角色 / 场景 / 关键道具

角色至少包含：

- 名称；
- 剧情功能；
- 基准外观；
- 时间范围内状态。

场景至少包含：

- 场景名称；
- 时间范围；
- 空间关系；
- 环境细节。

关键道具至少包含：

- 名称；
- 时间范围；
- 外观 / 状态；
- 剧情功能或使用方式。

这意味着该节点已经是一个完整的**业务可读 Source Understanding 文档**，而不是某个单一工具的 raw 输出。

---

# 3. 对 V3 Artifact 设计的直接结论

V3 当前已有正式 ArtifactType：

```text
SOURCE_VIDEO
SOURCE_DIALOGUE
SHOT_ANCHORS
SOURCE_BIBLE
STORY_SKELETON
RHYTHM_SKELETON
...
```

本次实测后，`SOURCE_BIBLE` 的产品语义正式定义为：

> **《源作概览分析》：整集原片理解形成的用户可读、可编辑、可版本化正式 Source Understanding Artifact。**

第一版至少应能表达：

```text
SOURCE_BIBLE
├─ 素材基线
├─ 整体分析
├─ 时间化原剧本 / 剧情时间线
├─ 人物候选与人物关系
├─ 场景
├─ 关键道具
├─ 关键事件 / Story Beats
└─ 对 Source Evidence 的 provenance 引用
```

`SOURCE_BIBLE` 不等于：

```text
SHOT_ANCHORS
ASR raw segments
OCR raw detections
模型原始 response
聊天消息
```

---

# 4. Source Evidence 与画布文档必须分离

本次实测尤其重要的一点是：用户点击的是：

```text
合规微调后重新写入画布
```

也就是说，画布中的《源作概览分析》文本可能经过平台合规修改。

因此 V3 必须坚持：

```text
SOURCE_DIALOGUE / OCR Evidence
= 原片实际说了什么 / 写了什么
= canonical + provenance
= 不被合规改写静默覆盖

SOURCE_BIBLE / 源作概览分析
= 对原片事实的业务理解和用户可读表达
= 可以产生修订版本
```

禁止：

```text
合规微调 SOURCE_BIBLE
→ 反写覆盖 SOURCE_DIALOGUE 原文
```

正确关系：

```text
SOURCE_VIDEO
├─ derives → SHOT_ANCHORS
├─ derives → SOURCE_DIALOGUE / OCR Evidence
└─ + Evidence → SOURCE_BIBLE rev1

用户修订 / 合规微调
↓
SOURCE_BIBLE rev2
↓
rev1 保留
↓
依赖 rev1 的逐镜拉片 / Source Snapshot / Target 结果进入 STALE
```

如果只是展示层措辞调整、没有改变业务事实，后续可以通过结构化 diff / semantic fingerprint 优化无意义的全链重算；但第一版应优先 fail-safe，不能默默让旧下游继续冒充 CURRENT。

---

# 5. Canvas 与 Artifact Graph 的关系进一步明确

本次实测支持以下产品模式：

```text
Agent 生成业务结果
↓
写入画布节点
↓
用户查看 / 修改
↓
Agent 读取节点详情
↓
后续 Skill 继续工作
```

V3 应吸收这个体验，但不能把 Canvas UI 当数据库真相。

正式关系仍然是：

```text
SOURCE_BIBLE Artifact
= 业务真相 / revision / provenance / CURRENT-STALE

Canvas Text Node
= SOURCE_BIBLE 的可视化与编辑入口
```

未来画布节点必须引用正式 Artifact ID / revision，而不是把一份脱离 Artifact Graph 的 Markdown 文本当唯一真相。

---

# 6. P7 的正式产品输出契约

P7「整集多模态原片理解」完成后，普通用户不应只看到一个“模型执行成功”。

至少要看到一份正式《源作概览分析》：

```text
素材基线
整体分析
完整时间化原剧本
角色与关系
场景
关键道具
Story / Rhythm
```

并满足：

- `SOURCE_BIBLE` 有 revision；
- 有 input fingerprint；
- 记录完整 Episode 与 Source Evidence provenance；
- CURRENT / STALE 正确；
- 用户可读；
- 用户可修改；
- 修改走显式 Command；
- 修改生成新 revision，不覆盖历史；
- 下游依赖正确 STALE；
- GET / 打开页面不自动调用模型；
- 普通 UI 不暴露 ASR/OCR raw 技术细节；
- Source Evidence 原文仍可在专业核对模式中追溯。

---

# 7. P8 与后续 Skill 的读取方式

P8 逐镜精细拉片不应该重新从零猜整集剧情。

正确读取：

```text
完整 Episode
+
CURRENT SOURCE_BIBLE《源作概览分析》
+
CURRENT SHOT_ANCHORS
+
需要时读取 canonical Source Evidence
↓
逐镜精细拉片
```

这与实测中“写入画布后再读取节点详情继续工作”的产品行为一致，但 V3 后端实际读取的正式对象应是 Artifact Graph 中的 CURRENT `SOURCE_BIBLE` revision。

---

# 8. 当前开发边界

本次只校正架构和契约。

当前 main 仍然没有实现：

```text
P6 ASR / OCR Provider
P6 Source Dialogue Artifact
P7 整集多模态 Provider
P7 SOURCE_BIBLE 内容生成 / 编辑 API
Canvas View
P8 逐镜语义拉片
```

不能因为已经明确《源作概览分析》的目标结构，就把这些阶段写成已经开发完成。
