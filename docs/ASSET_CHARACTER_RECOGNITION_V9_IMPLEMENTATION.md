# Character V9 实现状态

目标方案：`docs/ASSET_CHARACTER_RECOGNITION_V9_PLAN.md`

## 当前正式状态：V9 Phase A

当前 Runtime profile：

```text
character-v9a-person-instance-safety-v8-identity
```

当前 Asset Run profile：

```text
f05-assets-v9a-person-instance-safety-v8-identity
```

这表示：V9 的 Person Instance 安全层已经进入正式链路，但完整 Person Gallery Identity 尚未启用。

## Phase A 已完成

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
6. V8 内部若重建 Track，V9A adapter 会在身份解析后再次重建 CLEAN-only Gallery；
7. Run/profile 必须明确标记 V9A，不能被旧 persistence 改回 V6。

## 当前暂时保留

身份决策暂时仍使用：

```text
V8 Anchor-first Confirm-then-Absorb
```

但只消费经过 V9A 清理后的 Track / Gallery Evidence。

因此当前版本不能称为“完整 V9 人物图身份识别”。

## Phase B：下一步

实现真正的 Person Gallery Feature：

```text
Person Instance crop
→ Person ReID
→ Clothing / appearance feature
→ body / visible-structure feature
→ Face feature（可选强证据）
→ 每个通道独立保留，不拼成一个黑盒 embedding
```

Phase B 验收重点：

- 无脸 CLEAN 人物图也能产生可用的人物图特征；
- Face 不能单独决定同一人物；
- 多张 Person Image 的综合一致性可解释；
- 污染图不参与正式 Gallery Feature。

## Phase C：Person Gallery Anchor-first

替换 V8 身份决策：

```text
从 CLEAN Person Evidence 选稳定多图组
→ Confirmed Gallery A
→ 所有剩余人物图先比 A
→ MATCH / AMBIGUOUS / CLEARLY_DIFFERENT
→ 只从 CLEARLY_DIFFERENT 中确认 B
→ 所有剩余再依次比较 A + B
→ 继续确认 C ...
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
