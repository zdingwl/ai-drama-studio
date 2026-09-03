# AI 拉片模块业务方案与 UI 基线

> 状态：当前重做基线（2026-09-03）
>
> 本文用于冻结“AI 拉片”阶段已经确认的业务边界、数据目标和页面结构。后续 UI、数据库、后端、API、前端实现必须以本文为基线；如果业务方案发生变化，应先修改本文并确认，再修改代码，避免实现逐步跑偏。

## 1. 模块定位

AI 拉片承接上一阶段已经完成的 `ShotRevision` / 分镜检测结果，目标不是展示算法中间结果，而是把原片转换成后续 H3 重拍可直接消费的“镜头级原片事实”。

本阶段同时负责：

1. 对每个分镜进行镜头级内容理解；
2. 提取人物、场景、关键道具、对白及 H3 重拍所需镜头信息；
3. 对分镜内出现的人物生成独立人物视觉样本（去背景 / Mask / Face Crop / Body Crop 等）；
4. 对不同分镜提取到的人物样本自动归并；
5. 无法可靠归并的人物进入人工确认，不允许低置信度强行合并；
6. 最终人物只在主界面展示一张最佳代表图，其余观察样本保存在数据库 / 资产存储中；
7. 人物归并完成后自动反向绑定所有相关分镜；
8. 支持单分镜拉片、重新拉片和整集拉片；
9. 支持分镜时间范围调整，调整后只使受影响分镜的拉片结果失效并要求重新拉片。

本阶段不负责目标人物设计、本土化、翻译、TTS、H3 视频生成、Lip Sync 或成片输出。

---

## 2. 单个分镜必须得到的正式结果

一个完成的 Shot Breakdown 至少包含以下业务信息。

### 2.1 基础信息

- Shot 编号
- 开始时间
- 结束时间
- 时长
- 原始 Reference Clip / 可播放分镜视频

### 2.2 人物

- 分镜中出现的正式 `SourceCharacter`
- 说话人绑定
- 人物位置
- 人物状态
- 服装 / 外观线索
- 表情
- 动作
- 人物之间的交互

### 2.3 场景

- 场景身份 / `SourceScene`（当已归并）
- 内景 / 外景
- 地点描述
- 时间（白天 / 夜晚等）
- 环境
- 光线
- 天气（适用时）

### 2.4 道具

优先提取剧情关键道具，而不是把所有背景物品都提升为正式业务资产。

重点包括：

- 关键道具名称
- 道具属于谁（适用时）
- 使用方式
- 是否参与剧情动作

### 2.5 对白

- Speaker
- 开始时间
- 结束时间
- Final Text
- ASR evidence
- OCR evidence
- 校正状态 / 是否需要人工确认

### 2.6 H3 重拍所需结构化镜头信息

不能只保存一个 VLM summary。至少拆分保存：

- Subject
- Action
- Expression
- Interaction
- Scene
- Prop
- Camera
- Framing
- Composition
- Motion
- Lighting
- Continuity

这些字段用于后续稳定组装 H3 重拍输入，而不是让后续模块再次从自然语言摘要猜结构。

---

## 3. 对白识别规则：ASR + OCR 融合

对白不能只依赖 ASR。

建议正式流程：

```text
原分镜音频
  ↓
ASR（文本 + 时间戳）
  ↓
同时读取画面字幕 OCR
  ↓
ASR 与 OCR 按时间轴对齐
  ↓
一致 → 直接采用
冲突 → 结合置信度、上下文和语言一致性校正
ASR 失败但 OCR 有字幕 → OCR 补充
OCR 缺失但 ASR 可靠 → 使用 ASR
双方都无法确定 → 标记“对白待确认”
```

正式业务层保存 `Final Dialogue`。ASR / OCR 原始结果作为 evidence 保存，不直接作为最终对白。

示例：

```text
ASR：我要走了
OCR：我先走了
Final：我先走了
```

页面默认只展示 Final Text；只有需要排查或人工确认时再查看 ASR / OCR 证据。

---

## 4. 人物提取：Observation 不是 Final Character

每个分镜检测到的人物先形成 `CharacterObservation`（人物视觉观察样本），不能直接成为正式人物。

每个 Observation 建议保存：

- 所属 Episode / Shot
- 原始时间戳
- 原始上下文画面
- Bounding Box
- Person Mask
- 去背景人物图
- Face Crop
- Upper Body Crop
- Full Body Crop（可获得时）
- 清晰度评分
- 正脸程度
- 遮挡程度
- 人物尺寸
- Face embedding
- Body / appearance embedding
- 服装、发型、外观等语义特征

人物 Mask / 去背景图的目的，是减少场景、旁人、道具和构图对人物身份匹配的干扰。

正式原则：

```text
CharacterObservation / Track / Face Detection
!=
SourceCharacter
```

---

## 5. 人物自动归并

不同分镜提取出的 CharacterObservation 需要进行自动人物归并。

示例：

```text
Shot 01 → Observation 001
Shot 02 → Observation 006
Shot 05 → Observation 012
Shot 09 → Observation 024
          ↓
系统判断为同一人物
          ↓
SourceCharacter 001
├ Observation 001
├ Observation 006
├ Observation 012
└ Observation 024
```

### 5.1 自动归并不能只看单一阈值

身份判断应组合：

- Face Identity
- Body Appearance
- Clothing
- Hair
- Tracking
- Shot continuity
- VLM semantic evidence

### 5.2 三级处理原则

**高置信度**：自动合并。

典型证据：同 Track / 高人脸一致性 / 人体外观一致 / 时间连续。

**明显不同**：保持为不同人物。

**中间模糊区**：进入人工确认，禁止强行合并。

例如：

- 背影
- 严重遮挡
- 只有半张脸
- 人物过小
- 两名演员外观高度相似
- 信息不足或证据冲突

---

## 6. 人工人物合并

人工页面不展示 embedding、Track ID 等技术字段作为主要决策信息。

用户需要看到的是：

- 两个或多个疑似人物的最佳代表图
- 分别来自哪些 Episode / Shot
- 系统判断“疑似同一人物”
- 简化后的置信度 / 原因提示（如需要）

用户主要做两类决定：

- 合并为同一人物
- 不是同一个人

人工确认只处理自动系统无法可靠判断的少数异常，不应成为日常主流程。

---

## 7. 最终人物展示规则

一个 `SourceCharacter` 可以拥有很多 CharacterObservation，但主界面只展示一张最佳代表图。

最佳展示图自动评分建议综合：

- 清晰度
- 人脸可见程度
- 正脸程度
- 人物尺寸
- 遮挡情况
- 曝光质量
- 人物整体信息完整度

示例：

```text
SourceCharacter 01
Display Observation = OBS_028
```

其余 Observation 不在主人物卡中展开，但必须保存在数据库 / 资产存储中，用于：

- 身份判断
- 人物重新归并
- Target Character 设计
- H3 参考
- 人物一致性 QC
- 重新选择展示图

原则：不展示 ≠ 删除。

---

## 8. 人物归并后自动回绑分镜

人物归并完成后必须自动更新所有对应 Shot 的正式人物绑定。

例如：

```text
Shot 01 → Observation A
Shot 04 → Observation B
Shot 08 → Observation C

A + B + C → SourceCharacter 01

最终：
Shot 01 → SourceCharacter 01
Shot 04 → SourceCharacter 01
Shot 08 → SourceCharacter 01
```

用户最终看到的是正式业务人物，不是 LocalSubject / Track / Observation 技术 ID。

---

## 9. 场景和道具原则

### 9.1 场景

场景同样允许先产生 `SceneObservation`，再进行自动归并形成 `SourceScene`，避免每个 Shot 重复创建“同一个办公室”。

场景通常比人物更容易自动归并，因此人工确认频率应低于人物。

### 9.2 道具

不要求把所有视觉物品都建成正式资产。

优先提升为 Key Prop 的对象：

- 戒指
- 合同
- 手机
- DNA 报告
- 项链
- 药瓶
- 文件袋
- 其他会影响剧情、人物动作或 H3 重拍一致性的物体

普通桌椅、鼠标、垃圾桶等背景物品只有在剧情 / 重拍控制需要时才提升为正式道具。

---

## 10. 分镜调整

AI 拉片工作台允许检查并调整 Shot 的时间范围。

支持的基础能力：

- 视频循环播放当前 Shot
- 查看开始 / 结束时间
- 调整开始时间
- 调整结束时间

后续可评估：

- 向前 / 向后延长
- 拆分 Shot
- 合并相邻 Shot

### 10.1 失效规则

任何改变 Shot 实际视频范围的操作都会改变拉片输入，因此受影响 Shot 的旧拉片结果必须失效。

```text
Shot 08
00:21.0–00:25.0
      ↓ 修改
00:20.5–00:26.0
      ↓
Shot 08 拉片结果 → STALE / 待重新拉片
```

只重新处理被修改的 Shot，不应无条件重跑整集。

---

## 11. 单分镜拉片与整集拉片

### 11.1 单分镜

每个 Shot 支持：

- `拉片`
- 已完成后 `重新拉片`

状态：

- 未拉片
- 排队中
- 拉片中（显示进度）
- 待人工确认
- 已完成
- 失败

### 11.2 整集拉片

顶部支持 `整集拉片`。

业务上每个 Shot 都拥有独立任务状态；某个 Shot 失败不能阻止后面的 Shot 继续。

最终整集可呈现：

```text
39 已完成
2 待确认
1 失败
```

失败 / 待确认 Shot 可单独处理，不需要重新跑整个 Episode。

---

## 12. 页面 UI 基线（待 UI 图确认）

### 12.1 左侧项目阶段导航

延续现有项目页面风格，保留项目进度和阶段入口。

建议阶段：

```text
① 原短剧视频
   上传、排序与镜头检测

② AI 拉片（当前）
   镜头内容理解与人物归并

③ 原片确认
   人物 / 场景 / 道具确认

④ 视频重做

⑤ 成片输出
```

阶段的最终命名以后可以统一，但不能把 ASR / OCR / VLM / Tracking 做成顶级用户页面。

### 12.2 工作区顶部

主要元素：

- 页面标题：AI 拉片
- 剧集下拉选择
- 当前剧集 Shot 数量
- 已完成 / 待确认 / 失败摘要
- 整集拉片按钮
- 整集任务运行时显示整体进度

### 12.3 Shot 列表

工作区内部左列：

- 搜索 / 状态筛选
- Shot 编号
- 缩略图
- 时间范围
- 拉片状态
- 点击后切换当前 Shot

筛选至少包括：

- 全部
- 未拉片
- 待确认
- 失败

### 12.4 当前 Shot 视频与调整

工作区中间区域：

- Shot 视频播放器
- 当前 Shot 编号
- 开始 / 结束时间
- Shot 时间调整入口
- 拉片 / 重新拉片按钮

播放器默认循环当前 Shot，便于核对。

### 12.5 拉片结果

工作区右侧展示当前 Shot 的正式业务结果，建议通过 Tab 或分组降低信息密度：

- 拉片信息
- 人物
- 场景 / 道具
- 对白

#### 拉片信息

- 镜头景别
- 机位 / 视角
- 运镜
- 构图
- 动作
- 表情
- 人物交互
- 光线
- H3 重拍描述 / 结构化镜头信息

#### 人物

展示当前 Shot 已绑定的 SourceCharacter：

- 最佳代表图
- 人物临时名称 / 正式名称（按阶段）
- 是否说话人

主页面不展示该人物的全部 Observation。

#### 场景 / 道具

- 当前 SourceScene / 场景观察
- Key Props

#### 对白

- Speaker
- 时间范围
- Final Text
- 校正状态

ASR / OCR 冲突时显示“对白待确认”，证据只在详情 / 确认交互中展开。

### 12.6 人物待确认入口

人物归并不长期占据主工作区。

顶部或状态区展示：

```text
人物待确认 3
```

点击后打开 Drawer / Modal，只处理无法自动归并的人物。

---

## 13. 推荐的数据关系

```text
Episode
  └─ Shot
      ├─ ShotBreakdown
      ├─ Dialogue
      ├─ CharacterObservation
      ├─ SceneObservation
      └─ PropObservation
```

人物关系：

```text
CharacterObservation
        ↓
CharacterCluster / Identity Resolution
        ↓
SourceCharacter
        ↓
ShotCharacterBinding
```

正式 SourceCharacter 不是检测框、Track 或单张人脸截图。

---

## 14. 自动化与人工确认边界

系统自动完成确定性高的工作：

- Shot 拉片
- ASR / OCR 对齐
- 高置信度人物归并
- 场景归并
- 最佳人物代表图选择
- 归并后的 Shot 人物回绑

只有高风险 / 证据不足的情况进入人工确认：

- 人物身份无法可靠合并
- ASR 与 OCR 无法确定最终对白
- 其他会导致正式原片事实错误的硬冲突

不要把普通算法 evidence 全部变成人工确认页面。

---

## 15. Shot 完成标准

一个 Shot 只有满足业务消费条件才算真正完成，不能以“模型进程成功退出”代替业务完成。

基础完成条件：

- 时间范围有效
- Reference Clip 可播放
- 人物已识别
- 人物已可靠归并到 SourceCharacter，或不存在人物
- 场景信息有效
- 关键道具已处理
- 对白已确定，或明确无对白
- Speaker 已正确绑定（有对白时）
- 动作信息有效
- 摄影语言有效
- H3 重拍需要的结构化信息完整

存在人物归并冲突或对白冲突：`待人工确认`。

模型 / Provider 失败：`失败`。

---

## 16. 当前 UI 设计阶段的目标

当前暂不写业务代码。

下一步先根据本文制作 AI 拉片页面 UI 图，重点通过 UI 图继续发现：

- 信息是否过多或过少
- 三栏布局是否合理
- 分镜列表是否需要更宽 / 更紧凑
- 视频区域是否够大
- 人物、场景、道具、对白如何展示最直接
- 人物待确认入口是否明显
- Shot 调整是否需要独立模式
- 整集 / 单 Shot 拉片状态是否清晰

UI 图确认并修订本文后，才进入数据库 → 后端 → API → 前端完整开发。
