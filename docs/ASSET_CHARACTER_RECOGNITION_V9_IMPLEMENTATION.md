# Character V9 实现状态

目标方案：`docs/ASSET_CHARACTER_RECOGNITION_V9_PLAN.md`

## 当前正式状态：V9 Phase B

当前 Runtime profile：

```text
character-v9b-person-multichannel-gallery-v8-identity
```

当前 Asset Run profile：

```text
f05-assets-v9b-person-multichannel-gallery-v8-identity
```

这表示：V9 的 Person Instance 安全层和人物图多通道特征层已经进入正式链路，但完整 Person Gallery Identity 尚未启用。

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
6. 临时 V8 内部若重建 Track，V9 adapter 会在身份解析后再次重建 CLEAN-only Gallery；
7. Run/profile 必须明确标记当前 V9 阶段，不能被旧 persistence 改回 V6。

## Phase B 已完成：人物图多通道特征

每个 Person Instance 的身份特征只从该人物区域提取，整帧背景不能参与人物身份特征。

正式通道：

```text
Person Instance
├─ person_reid          # YoutuReID，人体外观主通道
├─ clothing_upper       # 上半身 HSV/Lab 颜色 + 梯度纹理
├─ clothing_lower       # 下半身 HSV/Lab 颜色 + 梯度纹理
├─ body_hist            # 历史轻量身体颜色支持通道
├─ body_structure       # 粗粒度可见身体结构 / 梯度描述
└─ face                 # 可选 SFace 强证据，不是人物本身
```

硬合同：

1. 不生成一个不可解释的“人物总 embedding”；
2. 各通道独立保存，Phase C 可分别判断 ReID / 服装 / 身体 / Face 的支持与冲突；
3. Face 缺失时，CLEAN Person Image 仍然必须有可用人物图特征；
4. Face 只能作为可选强证据，不能单独定义人物身份；
5. 不自动生成性别等人口属性作为视觉身份通道；只使用可观察的外观特征；
6. Track / Candidate Gallery 代表图质量改为 whole-person quality，不要求人脸突出；
7. 每张正式 Gallery JPG 同时保存 `features_XX.npz`，各通道分别落盘；
8. `gallery.json` 保存 feature version、通道列表、向量维度、Person Instance/crop 来源；
9. 改变人物框外的整帧背景，不得改变该 Person Instance 的人物图特征。

Phase B feature version：

```text
v9b-person-multichannel-1
```

## 当前暂时保留

身份决策暂时仍使用：

```text
V8 Anchor-first Confirm-then-Absorb
```

但它只能消费经过 V9A/B 清理后的 Person Instance / CLEAN Gallery Evidence。

因此当前版本仍不能称为“完整 V9 Person Gallery 身份解析”。

## Phase C：下一步 — Person Gallery Confirm-then-Absorb

Phase C 才真正替换临时 V8 身份决策：

```text
从 CLEAN Person Image 中找最稳定的一组人物图
→ Confirmed Gallery A
→ 所有剩余 Person Evidence 先和 A 多图、多通道比较
→ MATCH / AMBIGUOUS / CLEARLY_DIFFERENT

MATCH
→ 吸收到 A Gallery

AMBIGUOUS
→ UNRESOLVED
→ 不创建 A2

CLEARLY_DIFFERENT
→ 才能进入下一人物 seed pool

再确认 Gallery B
→ 所有剩余依次比较 A + B
→ 再确认 C ...
```

Phase C 必须使用多通道、可解释判定：

```text
ReID score
clothing upper/lower scores
body scores
Face score（可选）
same-frame cannot-link
multi-image support
```

不能回退成：

```text
一张脸 / 一个 Track / 一个总 embedding
→ 新建人物
```

Final Character 数量只能来自 Confirmed Person Gallery。

## Phase D：Final Gate / UI

最终切换：

```text
CONFIRMED Person Gallery
AND 多张 CLEAN Person Images
AND no identity conflict
→ Final Character
```

同时 UI 单独展示 UNRESOLVED Person Evidence，不计入人物数量。
