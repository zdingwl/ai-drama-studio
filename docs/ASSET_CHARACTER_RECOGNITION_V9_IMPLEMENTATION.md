# Character V9 / V9.1 实现状态

目标方案：`docs/ASSET_CHARACTER_RECOGNITION_V9_PLAN.md`

## 当前正式状态：V9.1 + V9D Final Gate

Character Runtime profile：

```text
character-v9.1-person-gallery-progressive-anchor
```

正式 Asset Run profile：

```text
f05-assets-v9.1-confirmed-person-gallery-final-gate
```

当前正式主链：

```text
Frame / Shot
→ Multi-Person Detection
→ 每个人拆成独立 Person Instance
→ CLEAN / OCCLUDED / CONTAMINATED / PARTIAL
→ 单人人物图多通道特征
→ Mature MOT
→ CLEAN Person Images
→ seed 只启动人物图库
→ 找跨 Shot strong partner
→ Progressive Proto Gallery
→ 多视角逐步扩展
→ Confirm Gallery A
→ 剩余人物图全部先和 A 的整个 Gallery 比较
→ Confirm Gallery B
→ 剩余全部比较 A + B
→ Confirm Gallery C ...
→ V9D Final Gate
→ Final Character / UNRESOLVED Evidence 分层
```

## A. Person Instance 安全层

硬合同：

1. 整帧不能作为正式人物身份图；
2. 同一帧多人必须先拆成独立 Person Instance；
3. OCCLUDED / CONTAMINATED / PARTIAL 只能作为 Evidence；
4. synthetic face fallback 不允许作为 CLEAN Gallery seed；
5. same-sample 不同人物写入 cannot-link；
6. Track 数量不能决定 Character 数量。

## B. 单人人物图多通道特征

每个 Person Instance 单独保留：

```text
person_reid
clothing_upper
clothing_lower
body_hist
body_structure
face(optional)
```

不生成不可解释的“人物总 embedding”。Face 是可选强支持证据，不是人物本身，也不是 Final Gate。

## C. V9.1 Progressive Person Gallery

正式入口：

```text
engine/app/character_identity_v91.py
```

V9C 曾经还有两个单图假设：

```text
问题 1：
seed 图
→ 要求其它支持图都直接 MATCH seed

问题 2：
人物确认以后
→ 后续图片必须同时直接 MATCH 固定多张 Gallery 图
```

这会造成：同一个人从正面 → 侧面 → 低头时，虽然相邻视角之间很稳定，但因为远端视角不像第一张 seed，人物图库建不起来，或者后续 Shot 无法挂回已确认人物。

V9.1 改为：

```text
高质量 seed
→ 找一个跨 Shot strong partner
→ 得到 Proto Gallery
→ 第三张只需要得到 Proto Gallery 的多视角支持
→ Gallery 扩大
→ 第四张继续和扩大的 Gallery 比
→ >=3 个独立 CLEAN Shot 后才允许 Confirm
```

seed 只负责启动，不再定义人物身份。

### 已确认人物的后续吸收

```text
新 Person Image X
→ 和人物 A 的整个 Gallery 比较

多个视角支持 A
→ MATCH / 吸收

同时对 A、B 都很像
→ AMBIGUOUS / UNRESOLVED

明确不属于任何已确认 Gallery
→ 才进入新人发现流程
```

这样一个已确认人物的正面、侧面、低头、坐姿等图可以由 Gallery 内不同视角分别支持，不要求它们都像某一张固定人物图。

### 新人物 Novelty

V9C 曾经存在：

```text
新人物组里只要任意一张图
对已有 A/B = AMBIGUOUS
→ 整组禁止成为新人
```

V9.1 改为 Gallery-level novelty：

```text
一张 AMBIGUOUS
+ 多个独立 Shot 明确 DIFFERENT
+ 新组内部多视角稳定
→ 可以确认新人物
```

但下面情况仍然禁止创建 A2/B2：

```text
>=2 个 Shot MATCH 已有人物
或
对已有 Gallery 存在特别强的单次 MATCH
或
1 个 MATCH + 其它 AMBIGUOUS 支持
```

### 新人物自动确认门槛

```text
>= 3 个独立 Shot
+ >= 3 张 CLEAN Person Images
+ Progressive multi-view consistency
+ 与全部已确认 Gallery 做完比较
+ Gallery-level 明确 novelty
+ no hard identity conflict
```

Partial / OCCLUDED / CONTAMINATED 永远不能 seed 新人物。

## D. Final Gate

正式入口：

```text
engine/app/asset_final_gate_v9.py
```

正式发布条件：

```text
identity_status == RESOLVED
AND resolver in {
  person-gallery-anchor-first-v9c,      # 历史 V9C Run
  person-gallery-progressive-v9.1       # 当前正式 V9.1
}
AND confirmed_gallery_shots >= 3
AND confirmed_gallery_images >= 3
→ Final Character
```

Face 不是 Final Gate。

```text
Confirmed Person Gallery
+ 3+ CLEAN 独立 Shot
+ face_images == 0
→ 仍可成为 Final Character
```

UNRESOLVED 永远不物化 Final Character。

## UI

正式页面：

```text
frontend/src/components/AssetStageV4.vue
```

V9D 早期曾把每条未归属 Track 都铺成“待解析人物”卡片，真实视频上可能出现 100+ 个碎片，容易误解成系统识别出了 100 多个人。

现在改为：

```text
Person Gallery：N 个 Final Character
待归属 Evidence：M 条
```

未归属 Evidence 是内部 Track / Person Image 碎片：

- 不计入人物数量；
- 不在主页面逐卡展开；
- 不再命名成“待解析人物001/002/...”给用户造成错觉；
- 继续保留在 AI Evidence 中用于后续 Gallery 吸收与诊断。

## 回归测试

核心测试：

```text
engine/tests/v2/test_character_person_instance_v9.py
engine/tests/v2/test_character_person_features_v9.py
engine/tests/v2/test_character_identity_v9c.py
engine/tests/v2/test_character_identity_v91.py
engine/tests/v2/test_character_v9c_runtime_wiring.py
engine/tests/v2/test_asset_final_gate_v9.py
engine/tests/v2/test_asset_final_gate_v91.py
engine/tests/v2/test_asset_final_gate_v9_wiring.py
```

V9.1 新增锁定：

1. 同一人物正面 → 半侧面 → 侧面 → 低头可以通过 Progressive Gallery 形成 1 个身份；
2. 后续人物图可以通过整个 Gallery 的多视角支持挂回已确认人物；
3. 一个新人物组只有一张图对 A 模糊相似，但其它多 Shot 明确不同，不得因此隐藏整个第三人物；
4. Partial-only 仍不能创建人物；
5. 3 个真人 + 大量碎片最终仍只能产生 3 个 Confirmed Gallery。

## 完整验收目标

对于真实 3 人视频：

```text
Person Track             可以很多
Partial Evidence         可以很多
待归属 Evidence          可以存在
Confirmed Person Gallery = 3
Final Character           = 3
```

同时每个 Final Character 的 Shot 覆盖应随着 Progressive Gallery 吸收增加，而不是只保留最初 3~4 个 seed Shot。

> 当前远程执行环境仍无法解析 `github.com`，GitHub 当前也没有 CI status。因此“测试已提交”不等于“测试已通过”；以本机 pytest / frontend typecheck 为准。
