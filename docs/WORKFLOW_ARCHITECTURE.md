# AI Drama Studio — User Workflow Architecture

Status: CONFIRMED  
Official Baseline: `main`

> 本文件定义 **用户真正看到和操作的生产流程**。
> `docs/FEATURE_SEQUENCE.md` 中的 Feature 继续作为内部工程能力、数据 Contract 和回归边界，但不再要求 `一个 Feature = 一个页面 = 用户点一次`。

---

# 1. 核心原则

正式原则：

```text
Feature = 内部工程职责 / 数据边界
Workflow = 用户操作步骤
```

禁止继续使用：

```text
一个后端模块
= 一个导航
= 一个页面
= 一次用户操作
```

正确方式：

```text
多个内部能力
→ Workflow Orchestrator
→ 一个用户动作
→ 一个连续工作区
```

内部模块仍保持单一职责，用户流程必须尽量少步骤、少初始化、少技术概念。

---

# 2. 用户主流程

V1 用户主流程固定为：

```text
01 导入原片
↓
02 拉片
↓
03 人物对白
↓
04 剧本 / 重制设计
↓
05 生成制作
↓
06 最终合成 / 导出
```

左侧导航、项目总览和“下一步”按钮以后全部按照 Workflow，而不是按内部 Feature 编号组织。

---

# 3. Workflow 01 — 导入原片

## 用户动作

用户只操作一次：

```text
项目名称
原片文件
原片语言
目标语言
目标地区
保存位置
↓
[创建并导入]
```

## 系统内部一次完成

```text
create_project()
↓
import_source_video()
↓
FFprobe / Source metadata
↓
preprocess_source_video()
↓
proxy.mp4
+ audio.wav
+ thumbnail.jpg
+ Source/Proxy/Audio time mapping
↓
项目初始化完成
```

内部能力对应旧：

```text
F01 创建项目
F02 上传原视频
F03 视频预处理
```

但用户不再进入三个页面分别操作。

## 进度 UI

```text
创建项目          ✓
导入原视频        ✓
读取媒体信息      ✓
生成分析视频      ✓
提取音频          ✓
初始化完成        ✓
```

## 失败原则

Workflow 必须记录当前阶段并可明确恢复/重试。

不得因为后半段失败就留下一个用户不知道如何处理的“空项目”。

底层 F01/F02/F03 的数据 Contract 和 Stable Snapshot 不因 Workflow 合并而失效。

---

# 4. Workflow 02 — 拉片

## 用户动作

```text
[开始拉片]
```

## 系统内部

```text
F03 Proxy
↓
F04 自动 Shot Detection
↓
自动创建 F05 Shot Edit Set / Final Shot Draft
↓
直接进入三栏镜头工作台
↓
人工调整
↓
确认 Final Shots
```

用户不需要知道或点击：

```text
initialize_shot_workbench()
```

它是 Workflow Orchestrator 的内部动作。

## 用户页面

自动检测完成以后直接进入同一个“拉片”工作区。

页面允许：

```text
播放
查看自动切镜
修改边界
拆分
合并
确认
```

不再设置独立的“自动拉片页面”和“镜头初始化页面”作为必须操作步骤。

---

# 5. Workflow 03 — 人物对白

“人物对白”的最终产品不是 Character Candidate，而是：

```text
演员 / 角色视觉身份
+
该演员说了哪些对白
+
每句对白的 Source 时间
```

## 自动分析链路

```text
confirmed Final Shots
+ F03 Proxy
+ F03 Audio
↓
A. 演员视觉识别
   Face Detection
   Face Track
   Face Embedding
   Cross-shot Actor Clustering
↓
B. 源对白识别
   Whisper ASR
   Dialogue start/end/text
↓
C. Speaker 分离
   Speaker Diarization / Voice Cluster
↓
D. Speaker ↔ Actor 匹配
   Dialogue time
   + Final Shot
   + Actor visual presence
   + speaker continuity
   + confidence
↓
Actor Dialogue Draft
```

## 自动结果

示例：

```text
演员 #01
头像
出现镜头：#002 #004 #005 ...

对白：
00:01.120 - 00:02.360  你怎么会在这里？
00:07.480 - 00:09.020  我已经跟你说过很多次了。
```

## 未归属对白

必须支持：

```text
未归属对白
```

如果：

```text
演员不在画面
多人同时在画面
Speaker/Actor 匹配置信度不足
```

不得强行绑定演员。

## 人工确认

人物和对白放在同一个人工工作区修正：

```text
合并/拆分演员
删除误检/路人
演员命名
对白文字修改
对白起止时间修改
对白拆分/合并
对白从演员 A 改到演员 B
处理未归属对白
最终确认
```

因此原来 Candidate-only 的 F06 页面只能视为“演员视觉 Evidence 调试界面”，不能再作为人物对白 Workflow 的最终页面。

---

# 6. Workflow 04 — 剧本 / 重制设计

后续详细 Contract 另行设计。

目标输入至少包含：

```text
Final Shots
Final Actor/Character
Final Source Dialogue
Scene / Story Context
```

输出面向重制制作，而不是继续暴露底层分析步骤。

---

# 7. Workflow 05 — 生成制作

内部可以包含很多 Capability：

```text
选角
Character Bible
Scene Bible
本土化对白
Shot Specification
视频生成
TTS
Lip Sync
QC
```

但页面应按生产工作流组织，不按每一个算法模块单独做左侧一级导航。

---

# 8. Workflow 06 — 最终合成 / 导出

内部包括：

```text
音频组装
字幕
最终合成
整集 QC
导出
```

用户最终操作保持连续。

---

# 9. Orchestrator 规则

建议新增业务编排层：

```text
ProjectImportWorkflow
ShotAnalysisWorkflow
CharacterDialogueWorkflow
```

Orchestrator 只负责编排已有业务函数、阶段状态和失败恢复。

禁止 Orchestrator：

```text
复制底层 SQL
复制 FFmpeg 算法
复制模型推理
破坏 F01-F05 已冻结数据 Contract
```

典型结构：

```text
Controller
→ Workflow Orchestrator
→ Existing Feature Services
→ DB / Media / Model
```

---

# 10. 冻结能力如何处理

F01-F05 的 `STABLE / FROZEN` 表示：

```text
数据 Contract
业务核心行为
时间轴规则
ID 规则
安全重跑规则
```

已经稳定。

Workflow 重构允许改变：

```text
导航
页面组合
用户点击次数
Controller 编排入口
自动调用顺序
```

但不允许为了简化 UI 破坏已冻结底层 Contract。

---

# 11. 当前重构优先级

```text
P0-1  导入原片 Workflow
P0-2  拉片 Workflow
P0-3  人物对白 Workflow 重新设计
```

在 P0-1 / P0-2 完成前，不继续扩大 Candidate-only F06 页面。

F06 当前算法代码可以保留作为 Actor Visual Evidence 能力，但其旧产品定义已被本文件取代。
