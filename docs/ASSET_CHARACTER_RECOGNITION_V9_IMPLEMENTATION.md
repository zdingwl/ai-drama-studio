# Character V9 实现状态

目标方案：`docs/ASSET_CHARACTER_RECOGNITION_V9_PLAN.md`

## 当前正式状态：V9 Phase C

当前 Runtime profile：

```text
character-v9c-person-gallery-anchor-first
```

当前 Asset Run profile：

```text
f05-assets-v9c-person-gallery-anchor-first
```

这表示：Person Instance 安全层、人物图多通道特征层、Person Gallery Anchor-first 身份解析已经进入正式链路。

当前尚未完成的是 Phase D：Final Gate / UI 对 CONFIRMED Person Gallery 的最终发布规则和 UNRESOLVED 独立展示。

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
→ CLEAN-only Candidate Gallery
→ CLEAN Person Instance crop 持久化
```

硬合同：

1. 整帧不能作为正式人物 Gallery 图；
2. 同一帧多人必须先拆 Person Instance；
3. OCCLUDED / CONTAMINATED / PARTIAL 只能作为 Evidence；
4. synthetic face fallback 不允许作为 CLEAN Person Gallery seed；
5. Gallery 保存前重新执行 Person Instance safety 校验；
6. Run/profile 必须明确标记当前 V9 阶段，不能被旧 persistence 改回 V6。

## Phase B 已完成：人物图多通道特征

每个 Person Instance 的身份特征只从该人物区域提取，整帧背景不能参与人物身份特征。

正式通道：

```text
Person Instance
├─ person_reid          # YoutuReID，人体外观主通道
├─ clothing_upper       # 上半身 HSV/Lab 颜色 + 梯度纹理
├─ clothing_lower       # 下半身 HSV/Lab 颜色 + 梯度纹理
├─ body_hist            # 轻量身体颜色支持通道
├─ body_structure       # 粗粒度可见身体结构 / 梯度描述
└─ face                 # 可选 SFace 强证据，不是人物本身
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

Phase B feature version：

```text
v9b-person-multichannel-1
```

## Phase C 已完成：Person Gallery Anchor-first / Confirm-then-Absorb

正式身份解析已经停用 V8，入口为：

```text
engine/app/character_identity_v9c.py
```

核心状态机：

```text
从 CLEAN Person Images 中选择高质量 seed
→ 找跨 Shot、多通道一致的稳定组
→ Confirmed Gallery A

所有剩余 CLEAN Person Images
→ 先与 A Gallery 比较

MATCH
→ 吸收到 A

AMBIGUOUS
→ UNRESOLVED
→ 禁止用它创建 A2

DIFFERENT
→ 才能进入新人物 seed pool

确认 Gallery B
→ 所有剩余再次依次比较 A + B
→ 再确认 Gallery C ...
```

新人物自动确认硬门槛：

```text
>= 3 个独立 Shot
+ >= 3 张 CLEAN Person Images
+ Person ReID / clothing / body / optional face 多通道一致
+ 与全部已确认 Gallery 明确不同
+ 无 same-sample cannot-link 冲突
```

Phase C 的身份判定保留可解释通道：

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

禁止回退成：

```text
一张脸
或一个 Track
或一个总 embedding
→ 新建人物
```

### Face 规则

Face 是支持证据，不是人物定义。

```text
Face 相似 + Person 图整体不支持
→ 不能直接 MATCH
```

高质量 Face 明显冲突可以作为强负证据，帮助证明两组 Person Images 不是同一个人。

### Partial / OCCLUDED / CONTAMINATED

这些 Evidence 不参与新人物 seed。

只允许：

```text
与已确认 Person Gallery 做更严格的多 Shot、多通道回挂
或
UNRESOLVED
```

绝不能增加 Final Character 数量。

### Track 规则

Track 只负责存在性和时序组织。

```text
1 个真人
→ 可以产生很多 Track
→ Confirmed Person Gallery 仍只能是 1
```

V9C 会按人物图 Evidence 重新分配 Track 内 Observation；一个污染 Track 不再天然等于一个身份。

## Phase C 回归合同

测试文件：

```text
engine/tests/v2/test_character_identity_v9c.py
```

锁定：

1. 3 个真人 + 多 Track / Partial fragment → 只能 3 个 Confirmed Gallery；
2. 无 Face 的 CLEAN 多 Shot 人物图可以确认人物；
3. 已确认 A 后，和 A 有中等相似但不够确定的稳定碎片必须 UNRESOLVED，不能创建 A2；
4. 只有 2 个 Shot 的组不能自动发布新人物；
5. Partial-only 不能创建人物；
6. Face 单通道相似不能直接 MATCH；
7. same-sample cannot-link 优先级高于视觉相似度。

注意：当前远程执行环境无法解析 `github.com`，所以这些测试目前为“已写入 main、待本机执行”，不能标记为已通过。

## Phase D：下一步 — Final Gate / UI

Phase D 需要把旧 Final Gate 的“Face anchor”历史假设彻底移除。

最终规则应为：

```text
CONFIRMED Person Gallery
AND >= 3 个独立 CLEAN Person Image / Shot 支持
AND no identity conflict
→ Final Character
```

Face 不再是 Final Character 的必要条件。

UI 需要分开：

```text
人物库
→ 只显示 Final Character

待解析人物 Evidence
→ UNRESOLVED
→ 不计入人物数量
→ 可人工挂到已有角色 / 确认为新人 / 标记无效
```

只有 Phase D 完成后，V9 才算完整闭环。
