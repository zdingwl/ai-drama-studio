# Character V9 实现状态

目标方案：`docs/ASSET_CHARACTER_RECOGNITION_V9_PLAN.md`

## 当前正式状态：V9 Phase D 完整闭环

Character Runtime profile：

```text
character-v9c-person-gallery-anchor-first
```

正式 Asset Run profile：

```text
f05-assets-v9d-confirmed-person-gallery-final-gate
```

含义：

- V9A Person Instance 安全层已启用；
- V9B 单人人物图多通道特征已启用；
- V9C Person Gallery Anchor-first / Confirm-then-Absorb 身份解析已启用；
- V9D Final Gate 已启用；
- UNRESOLVED 已在 UI 与 Final Character 分层。

正式人物主链：

```text
Frame / Shot
→ Multi-Person Detection
→ 每个人拆成独立 Person Instance
→ CLEAN / OCCLUDED / CONTAMINATED / PARTIAL
→ 单人人物图多通道特征
→ Mature MOT
→ CLEAN Person Gallery
→ Confirm Gallery A
→ 剩余人物图全部先比较 A
→ Confirm Gallery B
→ 剩余全部比较 A + B
→ Confirm Gallery C ...
→ V9D Final Gate
→ Final Character / UNRESOLVED Evidence 分层
```

## Phase A 已完成：Person Instance 安全层

```text
12fps Person / Partial Detection
→ 同帧多人拆成独立 Person Instance
→ instance_id
→ person_bbox
→ person_crop_bbox
→ CLEAN / OCCLUDED / CONTAMINATED / PARTIAL
→ same-sample spatial cannot-link Evidence
→ Mature MOT
→ CLEAN-only Track Representative
→ CLEAN Person Instance crop 持久化
```

硬合同：

1. 整帧不能作为正式人物 Gallery 图；
2. 同一帧多人必须先拆 Person Instance；
3. OCCLUDED / CONTAMINATED / PARTIAL 只能作为 Evidence；
4. synthetic face fallback 不允许作为 CLEAN Person Gallery seed；
5. Gallery 保存前重新执行 Person Instance safety 校验；
6. 同一采样时刻空间不同的人物写入 cannot-link；
7. Track 数量不能决定 Character 数量。

## Phase B 已完成：人物图多通道特征

每个 Person Instance 的身份特征只从该人物区域提取，整帧背景不能参与人物身份特征。

正式通道：

```text
Person Instance
├─ person_reid
├─ clothing_upper
├─ clothing_lower
├─ body_hist
├─ body_structure
└─ face                 # 可选支持证据
```

硬合同：

1. 不生成一个不可解释的“人物总 embedding”；
2. 各通道独立保存；
3. Face 缺失时，CLEAN Person Image 仍然可以提供人物身份依据；
4. Face 不能单独定义人物身份；
5. 不自动生成人口属性作为视觉身份通道；只使用可观察外观；
6. Gallery 代表图质量以 whole-person 为主；
7. 每张正式 Gallery JPG 同时保存 `features_XX.npz`；
8. `gallery.json` 保存 feature version、通道、向量维度和 Person Instance 来源；
9. 改变人物框外背景，不得改变 Person Instance 特征。

Feature version：

```text
v9b-person-multichannel-1
```

## Phase C 已完成：Person Gallery Anchor-first / Confirm-then-Absorb

正式身份入口：

```text
engine/app/character_identity_v9c.py
```

核心状态机：

```text
从 CLEAN Person Images 中选择高质量 seed
→ 找跨 Shot、多通道一致的稳定组
→ Confirmed Gallery A

所有剩余 Person Images
→ 必须先与 A 比较

MATCH
→ 吸收到 A

AMBIGUOUS
→ UNRESOLVED
→ 禁止创建 A2

DIFFERENT
→ 才能进入下一人物 seed pool

确认 Gallery B
→ 剩余人物图全部依次比较 A + B
→ 再确认 Gallery C ...
```

新人物自动确认门槛：

```text
>= 3 个独立 Shot
+ >= 3 张 CLEAN Person Images
+ ReID / clothing / body / optional face 多通道一致
+ 与全部已确认 Gallery 明确不同
+ 无 same-sample cannot-link 冲突
```

身份通道保持可解释：

```text
person_reid
clothing_upper
clothing_lower
body_hist
body_structure
face(optional)
same-sample cannot-link
multi-shot gallery support
```

禁止：

```text
一张脸
或一个 Track
或一个总 embedding
→ 新建人物
```

### Face

Face 是可选支持证据，不是人物定义。

```text
Face 相似 + 人物图整体不支持
→ 不能直接 MATCH
```

高质量 Face 明显冲突可以作为强负证据。

### Partial / OCCLUDED / CONTAMINATED

不能参与新人物 seed。

只允许：

```text
严格回挂到已确认 Person Gallery
或
UNRESOLVED
```

### Track

Track 只负责存在性和时序组织：

```text
1 个真人
→ 可以产生很多 Track
→ Confirmed Person Gallery 仍只能是 1
```

## Phase D 已完成：Final Gate

正式入口：

```text
engine/app/asset_final_gate_v9.py
```

正式路由：

```text
engine/app/asset_routes_v3.py
→ import asset_final_gate_v9.apply_analysis_to_assets
```

V9 Final Character 的唯一自动发布来源：

```text
identity_status == RESOLVED
AND resolver == person-gallery-anchor-first-v9c
AND confirmed_gallery_shots >= 3
AND confirmed_gallery_images >= 3
→ Final Character
```

### Face 不再是 Final Gate

V9D 明确允许：

```text
Confirmed Person Gallery
+ 3+ CLEAN 独立 Shot
+ 多通道人物图一致
+ face_images == 0
→ Final Character
```

因此不会再出现“人物图库已经稳定，但因为没有露脸而被 Final Gate 丢掉”的问题。

### UNRESOLVED

```text
identity_status == UNRESOLVED
→ 永远不物化 Final Character
→ AI Evidence 保留
→ 不计入人物资产数量
```

即使 UNRESOLVED Track 有高质量 Face，也不能绕过 Final Gate。

### Fail closed

对 V9 Run，如果 Candidate 写成 RESOLVED，但缺少：

```text
resolver
confirmed_gallery_shots
confirmed_gallery_images
```

则不允许物化 Final Character。

历史 pre-V9 Run 为了兼容旧数据，继续使用其历史 face-visible 安全门，不会被 V9D 静默重新解释。

## Phase D 已完成：UI 分层

正式页面：

```text
frontend/src/components/AssetStageV4.vue
```

UI 分成：

```text
Person Gallery / Final Character
→ 只统计 resolved_character_candidates

待解析人物 Evidence
→ 独立区域
→ 展示 Evidence cover / Shot / Track
→ 不进入 Final Character 数量
```

重要 UI 合同：

```text
face_visible != identity_status
```

UI 不再通过“有没有脸”猜测 Candidate 是否已确认，只读取正式 Evidence 分层结果。

资产后台任务完成后，`studio-task-finished` 会自动刷新待解析 Evidence 区域。

## 回归测试

Person Instance：

```text
engine/tests/v2/test_character_person_instance_v9.py
```

人物图特征：

```text
engine/tests/v2/test_character_person_features_v9.py
```

Person Gallery Identity：

```text
engine/tests/v2/test_character_identity_v9c.py
engine/tests/v2/test_character_v9c_runtime_wiring.py
```

Final Gate：

```text
engine/tests/v2/test_asset_final_gate_v9.py
```

V9D Final Gate 测试锁定：

1. `face_images=0` 的 Confirmed Person Gallery 仍可成为 Final Character；
2. 有脸的 UNRESOLVED 也不能成为 Final Character；
3. V9 RESOLVED 但缺 Person Gallery provenance 必须 fail closed；
4. 只有 2 个独立 Gallery Shot 不能绕过 Final Gate。

## 完整验收目标

对于真实 3 人视频：

```text
Person Track            可以很多
Partial Evidence        可以很多
UNRESOLVED              可以存在
Confirmed Person Gallery = 3
Final Character          = 3
```

如果结果不是 3，下一步排障只看 V9C Gallery 的 MATCH / AMBIGUOUS / DIFFERENT 证据，不再通过增加 Track、降低人脸阈值或事后按人数硬合并解决。

> 当前远程执行环境没有可用的本地仓库测试执行能力，GitHub 当前也没有 CI status。因此“代码/测试已提交”不等于“测试已通过”；必须以本机 pytest / frontend typecheck 为准。
