# Character V10：先采集 Person Evidence，再用人物模型分类

V10 取代 V9.x 正式身份链路。核心原因：V9.x 在身份分类之前对 Person Image 做了过早的 CLEAN / Gallery 过滤，导致正面图容易保留，而侧身、背影、多人同框拆出来的人物、短暂出现的人物容易在进入分类模型前被丢失。

## 唯一正式原则

```text
Frame / Shot
→ Person Detection
→ 一帧多人拆成多个独立 Person Instance
→ 每个 Person Instance 单独裁图
→ 先保存 Person Evidence
→ 再用人物模型比较 / 分类
→ 人物 A / B / C
→ 将分类结果回写 Person Evidence
→ 保存每个人的多视角 Person Gallery
→ Final Character
```

禁止：

```text
整帧 → 人物身份 embedding
单张 Face → Character
只有 CLEAN / 正脸 → 才能进入人物分类
Track 数量 → Character 数量
```

## 1. Person Evidence：先获取，后判断是谁

V10 将两个概念彻底分开：

```text
person_evidence_eligible
= 这张单人人物图是否值得保存和进入模型分类

person_seed_eligible
= 这张人物图是否可靠到可以参与创建一个新人物类别
```

因此：

```text
清晰单人图               → 保存 / 分类 / 可做 seed
侧身、背影               → 保存 / 分类 / 可做 seed（质量满足时）
多人同框拆出的独立人物 crop → 保存 / 分类 / 可做 seed（质量满足时）
OCCLUDED                  → 保存 / 分类；质量满足时可做 seed
CONTAMINATED              → 保存 / 分类 / 挂回已有身份；不单独 seed
PARTIAL                   → 保存 / 分类 / 挂回已有身份；不单独 seed
极小、无 ReID、几乎无人体信息 → 不进入自动身份分类
synthetic face fallback   → 不作为 Person Image
```

注意：`CLEAN` 是 crop 安全类别，不再是人物身份系统的入口许可证。

## 2. 多人同框

整帧永远不做人身份对比。

```text
一帧有 A / B / C
→ Person Detector 得到三个 bbox
→ A crop
→ B crop
→ C crop
→ 三份独立 Person Evidence
→ 分别进入人物模型分类
```

同一采样时刻空间不同的 Person Instance 写入硬约束：

```text
same sample + different Person Instance
→ cannot-link
```

即使两个人服装非常相似，也不能被合并成同一人物。

## 3. 人物模型分类

V10 主分类模型：

```text
YoutuReID Person Re-identification
```

它以完整人物 crop 为输入，用于跨正面 / 侧身 / 背影比较。

支持通道保持分离：

```text
person_reid        # 主模型信号
clothing_upper     # 支持
clothing_lower     # 支持
body_hist          # 支持
body_structure     # 支持
face               # 可选支持 / 强冲突证据
```

Face 不再是必要条件，也不能单独定义 Character。

不使用人口属性推断作为身份分类通道。

## 4. 分类方式

先从可靠、跨 Shot 的 Person Evidence 建立人物类别，再分类全部剩余 Evidence：

```text
可靠 Evidence → Identity A
所有其它 Person Evidence → 对比 A 的整个 Gallery
MATCH → A
AMBIGUOUS → UNRESOLVED
DIFFERENT → 保留为新人物候选

确认 B 后
→ 剩余 Evidence 对比 A + B

继续 C ...
```

新人物仍需要至少 3 个独立 Shot / 3 张可靠人物图支持，避免单个碎片制造 Character。

但是身份确认之后，侧身、背影、遮挡、多人同框拆出的 crop 可以用更严格的模型支持挂回人物 A/B/C。

## 5. MOT 不是人物入口门

MOT 只负责时序组织。

如果一个有效 Person Evidence 因出现时间短、遮挡或 MOT 断轨没有形成 Mature Track：

```text
有效 Person Evidence
→ Evidence-only singleton Track
→ 仍进入人物模型分类
```

因此“没有形成成熟 Track”不再等于“人物图丢失”。

## 6. 先落盘，再分类

每个 Run 会先建立：

```text
analysis/<run_id>/person_evidence/
```

其中包含：

```text
*.jpg          # 独立 Person Instance crop
*.npz          # ReID / clothing / body / optional Face 特征
manifest.json  # Shot / 时间 / bbox / class / cannot-link / 分类状态
```

初始状态：

```text
classification_status = UNCLASSIFIED
```

模型分类完成后，同一个 manifest 回写：

```text
classification_status = RESOLVED / UNRESOLVED
identity_ordinal = 1 / 2 / 3 ...
candidate_id = ...
```

这样可以明确区分：

```text
没有采集到人物 crop
vs
采集到了，但模型没有分类成功
```

## 7. Classified Person Gallery

确认人物后，保存的是多视角人物图库，而不是“正脸图库”：

```text
character_xxx/
├─ gallery_001.jpg
├─ gallery_002.jpg
├─ gallery_003.jpg
├─ features_001.npz
├─ features_002.npz
├─ ...
└─ gallery.json
```

允许包含：

```text
正面
侧身
背影
遮挡
多人同框中拆出来的单人 crop
局部 Evidence（已高置信挂回已有身份时）
```

每张 Gallery 图片保留 `instance_class / quality / reliability / Shot / source_time / feature channels`。

## 8. UI

资产页增加“人物图 Gallery”：

```text
人物 001
→ 展示模型真正分类到人物 001 的单人 crop

人物 002
→ 展示模型真正分类到人物 002 的单人 crop
```

这和 Shot 缩略图是两个不同概念：

```text
Person Gallery crop = 人物身份内容
Shot thumbnail      = 人物出现的镜头上下文
```

## 9. Track 代表帧

V10 不再：

```text
face_visible 优先
```

改为：

```text
Person Evidence eligible
→ 人物图质量 × 可靠度
→ 身体完整度
→ 清晰度
→ 检测置信度
→ Face 只作为最后的附加排序信息
```

历史 pre-V10 Run 保留旧排序兼容。

## 10. 正式版本

```text
Character Runtime:
character-v10-capture-first-model-classification

Asset Run:
f05-assets-v10-person-evidence-model-classification

Identity Resolver:
person-evidence-model-classifier-v10
```

## 11. 本项目真实视频验收标准

不能只验人物数量。

```text
真实人物 = 3
Final Character = 3
```

同时必须满足：

1. 每个人物能看到多 Shot 人物图；
2. 有实际出现时，侧身 / 背影 Evidence 不应因无脸而消失；
3. 多人同框时，各人物被拆成独立 Person crop 并分别分类；
4. 短暂人物实例即使 MOT 未连成轨，也必须保留 Person Evidence；
5. PARTIAL / CONTAMINATED 可以保存并挂回已有身份，但不能自己制造第 4 / 5 个人物；
6. `person_evidence/manifest.json` 中已采集的实例必须有明确 RESOLVED / UNRESOLVED 分类结果或保持可诊断状态。

## 12. 排障方法

以后不再猜阈值。

如果某个背影 / 侧身缺失，先看：

```text
analysis/<run_id>/person_evidence/manifest.json
```

### Crop 不存在

```text
→ Person Detection / Person Evidence policy 问题
```

### Crop 存在，但 classification_status = UNRESOLVED

```text
→ Person ReID / Gallery 分类问题
```

### Crop = RESOLVED，identity_ordinal 正确，但 UI 不显示

```text
→ Gallery 持久化 / API / UI 展示问题
```

这样检测、保存、分类、展示四层可以分别定位，不再用“最终人物数不对”反推所有层。
