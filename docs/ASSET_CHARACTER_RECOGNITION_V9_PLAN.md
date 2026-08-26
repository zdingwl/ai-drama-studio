# Character V9 人物资产提取重规划

> 状态：正式目标方案，供下一阶段实现与验收使用。
>
> 核心原则：**不是人脸识别，而是人物图识别；不是整帧识别，而是 Person Instance 识别；不是 Track 数量决定人物数量，而是稳定 Person Gallery 决定 Final Character。**

---

## 1. 目标

人物资产提取必须解决两类问题：

1. **不能多建人物**：同一个真人因为侧脸、背影、半身、遮挡、Track 断裂、Face fallback 等原因被拆成多个 Character。
2. **不能漏人物**：局部人体、背面、半身、贴边人物因为看不到完整人脸而直接消失。

V9 的正式目标不是“尽可能多地产生人物候选”，而是：

```text
Evidence 可以多
Track 可以多
UNRESOLVED 可以多
Final Character 必须少而准
```

Final Character 数量只能由**稳定的人物图库 Person Gallery**产生。

---

## 2. 不可违反的硬规则

### 2.1 不能拿整张 Frame 直接做人身份对比

一张画面里可能同时存在多个人。整帧只能用于 Person Detection / Scene Context，不能直接作为某一个人物的身份图。

```text
Frame
→ Multi-Person Detection
→ Person A / Person B / Person C
→ 分别裁成独立 Person Instance
→ 分别进入人物识别
```

身份识别的最小单位是 **Person Instance**，不是 Frame。

### 2.2 Face 只是一个证据通道，不是身份本身

人物匹配使用综合人物图特征：

```text
Person Gallery Match
= Body / Person ReID（主）
+ 服装 / 颜色 / 纹理外观（主）
+ 身体轮廓 / 可见结构（支持）
+ Face embedding（有脸时强证据）
+ 多张图一致性（必须）
+ 时间 / 同框 cannot-link（硬约束）
```

禁止：

```text
一张脸很像
→ 直接确认同一人物
```

正确方式：

```text
Face 很像
+ Person 图整体一致
+ 不存在时空冲突
→ 强支持同一人物
```

### 2.3 不自动从画面推断“性别”作为身份特征

视觉外观可以使用可观察特征，例如服装、发型、体型轮廓、身体外观等；不要把自动推断的性别身份作为人物合并/拆分的硬条件。

如业务以后存在人工填写的人物属性，可作为 Final Asset 元数据，但不作为视觉身份解析器的自动判断依据。

### 2.4 Track 不能创建人物

Person Track 只表示：

> “在这个 Shot 的这段时间里，有一个连续的人物实例。”

Track 可以断裂、重复、重建，因此：

```text
1 个真人
→ 可以产生 1 / 5 / 20 个 Track
→ Final Character 仍然只能是 1
```

### 2.5 Partial / Body-only 不能直接创建新人物

半身、背影、肩膀、手臂、贴边身体等必须保留 Evidence，但只能：

```text
挂回已确认 Person Gallery
或者
UNRESOLVED
```

不能因为一张 body-only 图创建新的 Final Character。

---

## 3. 正式主流程

```text
Source Shot
↓
12fps Person Observation
↓
Multi-Person Detection
↓
Person Instance Split
↓
Shot 内 Mature MOT
↓
Clean / Contaminated Person Crop 分类
↓
人物图特征提取
  ├─ Person ReID
  ├─ Clothing / Appearance
  ├─ Body shape / visible structure
  ├─ Face（可选）
  └─ 时空信息
↓
Anchor-first Person Gallery Builder
↓
先确认人物 A
↓
用人物 A Gallery 扫描全部剩余 Evidence
↓
再确认人物 B
↓
用 A + B 扫描全部剩余 Evidence
↓
继续确认 C ...
↓
剩余无法确认 → UNRESOLVED
↓
稳定 Person Gallery → Final Character
```

---

## 4. 多人同框处理

### 4.1 一帧多人必须先拆 Person Instance

假设同一帧检测到三个人：

```text
Frame
├─ Person A bbox
├─ Person B bbox
└─ Person C bbox
```

必须生成：

```text
Crop A → 独立人物 Evidence
Crop B → 独立人物 Evidence
Crop C → 独立人物 Evidence
```

禁止整帧直接加入任何一个人物 Gallery。

### 4.2 同一时刻不同 Person Instance 永久 cannot-link

如果同一采样时刻明确检测到两个空间不同的人：

```text
same frame
+ simultaneous
+ spatially distinct
→ cannot-link
```

后面即使 ReID 或衣服相似度很高，也不能合成同一个 Character。

### 4.3 Face → Person 必须一对一安全归属

Face 不能只使用“中心点落在人体框里”规则。

必须满足：

- Face 大部分位于 Person bbox 内；
- Face 位于人体合理上部区域；
- Face / Person 尺寸比例合理；
- 同一 Face 只能属于一个 Person；
- 同一 Person 同一时刻最多接收一个主 Face；
- Partial 大框不能抢旁边人的 Face。

未安全归属的 Face 可以保留独立 Face Evidence，但不能污染另一个 Person Instance。

### 4.4 Crop 污染分类

每个 Person Crop 必须标记：

```text
CLEAN
OCCLUDED
CONTAMINATED
PARTIAL
```

#### CLEAN

目标人物清楚，其他人物污染低。

用途：

- Person Gallery
- ReID
- Clothing / appearance
- Cover

#### OCCLUDED / CONTAMINATED

目标人物被另一人物明显遮挡或 crop 混入其他人。

用途：

- MOT continuity
- presence Evidence

禁止：

- 进入正式 Gallery
- 作为新人物 seed

#### PARTIAL

只有部分身体可见。

用途：

- Presence
- 尝试回挂已有人物

禁止：

- 创建新人物

---

## 5. 人物图库 Person Gallery

每个已确认人物维护一个多图 Gallery，而不是一个平均 embedding。

建议结构：

```text
CharacterGallery
├─ character_id
├─ representatives[]
│  ├─ shot_id
│  ├─ source_time_us
│  ├─ crop_path
│  ├─ quality
│  ├─ face_embedding?
│  ├─ person_reid
│  ├─ appearance_feature
│  ├─ body_feature
│  └─ cleanliness
├─ shot_ids[]
├─ hard_cannot_links[]
└─ status = CONFIRMED
```

Gallery 代表图应尽量覆盖：

- 正面；
- 侧面；
- 半身；
- 全身；
- 不同姿态；
- 有脸 / 无脸；
- 同一服装下不同光照。

同一个 Shot 不应塞大量近重复图片，避免 Gallery 被一个长镜头支配。

---

## 6. Anchor-first：先确认，再吸收

这是 V9 的核心身份算法。

### 6.1 第一个人物

从所有未解析 CLEAN Person Evidence 中，找质量最高的一组，而不是一张图。

Seed Group 至少满足：

- 多个独立 Shot；
- Person ReID 稳定；
- 服装/外观一致；
- 如果有 Face，Face 一致；
- 不存在 simultaneous cannot-link；
- Crop 大部分为 CLEAN。

确认后创建：

```text
Confirmed Gallery A
```

### 6.2 A 扫描剩余 Evidence

所有剩余 Person Evidence 必须先和 A 比较。

结果只有三种：

```text
MATCH
→ 吸收到 A

AMBIGUOUS
→ UNRESOLVED
→ 不创建人物

CLEARLY_DIFFERENT
→ 保留为下一人物候选
```

### 6.3 再确认 B

只能从 `CLEARLY_DIFFERENT` 的剩余 Evidence 里选择新 seed。

确认 B 前必须先证明：

```text
它不是 A 的困难角度 / 遮挡 / 换姿态 / Track fragment
```

确认 B 后：

```text
所有剩余 Evidence
→ 先比 A
→ 再比 B
```

之后同理确认 C、D……

### 6.4 创建新人物的硬条件

新 Gallery 必须同时满足：

1. 自身多图一致；
2. 有跨 Shot 支持；
3. 与所有已确认 Gallery 做过对比；
4. 没有明显匹配已有 Gallery；
5. 没有 ambiguous existing identity；
6. 不由单张 Partial / Body-only / Contaminated 图组成。

只要仍可能属于某个已有角色：

```text
宁可 UNRESOLVED
也不新建人物
```

---

## 7. 人物图匹配策略

### 7.1 不使用单一总 embedding

不同证据通道分别保留：

```text
face_score
reid_score
appearance_score
body_score
temporal_score
cannot_link
```

最终判断基于证据组合，而不是把全部特征拼成一个不可解释的向量后直接阈值判断。

### 7.2 推荐判定优先级

#### 强匹配

例如：

```text
高 ReID + 高 appearance
```

或：

```text
高 Face + 中高 ReID
```

或多张代表图持续支持。

#### 模糊匹配

例如：

```text
Face 中等
ReID 中等
服装很像
```

不能创建新人，也不要强行吸收，进入 UNRESOLVED。

#### 强冲突

例如：

```text
同一时刻空间不同
```

直接 cannot-link，优先级高于相似度。

---

## 8. Final Character 生成规则

Final Character 不再由以下任何单项直接产生：

- Face；
- Track；
- Person bbox；
- body-only；
- 两张相似图片；
- 一个 Shot。

只允许：

```text
CONFIRMED Person Gallery
→ Final Character
```

建议 Candidate 状态：

```text
CONFIRMED
UNRESOLVED
REJECTED_FRAGMENT
```

Final Gate：

```text
status == CONFIRMED
AND gallery_has_multiple_clean_person_images
AND no_identity_conflict
→ Final Character
```

没有脸不再自动判死刑；只要人物整体 Gallery 足够稳定，可以确认人物。

但单纯 body-only / partial 不能作为创建 Gallery 的初始 seed。

---

## 9. Shot Binding

人物身份和“这个 Shot 里有没有这个人”必须分开。

```text
Character Identity
≠
Shot Presence
```

当 Gallery A 已经确认后：

- 有脸图可以挂 A；
- 无脸全身图可以通过 ReID/appearance 挂 A；
- 半身图可以保守挂 A；
- 模糊 partial 可以保留 Evidence；
- 不确定时不强绑。

同一 Character 在一个 Shot 中即使产生多个 Track，Final Binding 也只保存一次。

---

## 10. UI 行为

人物库只显示 Final Character。

每个人物详情建议显示：

```text
人物001
├─ Final Gallery
├─ 已绑定 Shots
├─ Clean Evidence
├─ Body / Partial extensions
└─ Confidence / identity diagnostics
```

UNRESOLVED 不占“人物数量”，单独放入：

```text
待解析人物 Evidence
```

可以人工：

- 挂到人物001；
- 挂到人物002；
- 确认为新人物；
- 标记为非人物/无效碎片。

---

## 11. 回归测试硬指标

### T1：三真人，多 Track

```text
真实人物 = 3
Track = 30
Final Character 必须 = 3
```

### T2：同一人断轨

同一个人在同一个 Shot 中被拆成多个 Track：

```text
Final Character 不增加
```

### T3：多人同框

A / B 同一时刻同时出现：

```text
A != B 永久 cannot-link
```

### T4：整帧禁止入 Gallery

任何 Gallery representative 都必须有 `person_bbox / crop_path`。

不能保存整帧作为人物 Gallery 图。

### T5：Face 不是必要条件

同一人物三组 CLEAN Person 图，ReID / appearance 高度一致，但没有可用 Face：

```text
允许形成稳定 Person Gallery
```

前提：不能来自 partial / contaminated 单图。

### T6：Face 不是充分条件

Face 相似，但同一时刻检测到两个空间不同 Person：

```text
不得合并
```

### T7：局部身体不增加人物

大量 shoulder / arm / back / partial Evidence：

```text
可以挂回已有 Gallery
或 UNRESOLVED
Final Character 数不增加
```

### T8：服装相似不能误合

两个不同人穿相似衣服，同时出现或 Face/ReID 明确冲突：

```text
不得合并
```

### T9：同一人困难角度不能新建

人物 A 已确认，后续出现侧脸、低头、背面：

```text
先和 A Gallery 比
MATCH / AMBIGUOUS
不得直接创建 A2
```

### T10：三真人端到端

对已知真实为三个人的验收视频：

```text
Final Character = 3
人物 Shot Binding 可允许少量漏绑
但不得通过创建额外 Character 补偿漏绑
```

---

## 12. 开发顺序

### Phase A：Person Instance 安全层

1. 多人检测拆分；
2. Face→Person 一对一归属；
3. CLEAN / CONTAMINATED / PARTIAL 分类；
4. 禁止整帧进入 Gallery。

### Phase B：Person Feature Gallery

1. Person ReID；
2. appearance / clothing 特征；
3. Face 可选证据；
4. 多图 Gallery；
5. Gallery diversity。

### Phase C：Anchor-first Identity

1. 找高质量 seed group；
2. 确认人物 A；
3. A 全局吸收；
4. 剩余 Evidence 确认 B；
5. 依次继续；
6. Ambiguous 一律留 UNRESOLVED。

### Phase D：Final Gate / UI

1. Final 只发布 CONFIRMED Gallery；
2. UNRESOLVED 独立管理；
3. 人工挂回 / 新建 / 拒绝；
4. 不再用 Face-visible 作为 Final 的必要条件。

### Phase E：回归验收

必须先通过本文件 T1～T10，再替换当前正式人物提取链路。

---

## 13. 迁移原则

V6 / V7 / V8 的 Identity Resolver 不继续叠补丁。

正式迁移要求：

```text
旧 Evidence 数据模型可保留兼容
旧 Final Revision 不删除
新 Run 使用新 profile
新算法成功后再切 Current
失败时旧资产版本仍可恢复
```

建议新 Profile：

```text
character-v9-person-gallery-anchor-first
f05-assets-v9-person-gallery-anchor-first
```

---

## 14. 一句话产品定义

> **先把每帧中的每个人拆成独立人物图；用多张单人人物图建立稳定人物图库；先确认一个人物，再让后续所有人物图优先和已确认图库比较；只有确实不属于任何已有图库、并且自身多图一致的新人物，才允许创建新的 Final Character。**
