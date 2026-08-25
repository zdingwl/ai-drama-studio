# 03 资产 — Character Recognition V4

## 为什么重做

真实短剧资产矩阵回归暴露两类同时存在的问题：

```text
1. 漏检：画面明显有人，但 Shot Final Character 为空；
2. 碎片化：同一演员被拆成多个 人物 001 / 002 / 003 ...。
```

旧人物 Evidence 为：

```text
3 帧固定采样
+ YuNet / SFace
+ OpenCV HOG Person
+ HSV 服装直方图
+ 极保守 body-only 相邻 Shot 连接
```

这套策略解决了旧版“上千个假人物”，但过度保守，不能继续作为 Speaker / Dialogue 的身份基础。

## V4 正式链路

```text
Reference Clip
↓
自适应多帧采样（3 / 5 / 7 / 9）
↓
YOLOX Person Detection
↓
YuNet Face Detection
+ SFace Face Identity
↓
YoutuReID Body Identity
+ 轻量服装颜色 Evidence
↓
Shot-local Track
↓
Cross-shot Identity Clustering
↓
Resolved Candidate 二次去碎片
↓
RESOLVED / UNRESOLVED Character Evidence
```

### RESOLVED

至少拥有一个 Face/SFace identity anchor。

可以自动形成：

```text
Final Character
+ ShotCharacterBinding
```

该 Character 在其它 Shot 中允许通过 YoutuReID 延续，即使对应 Track 没露脸。

### UNRESOLVED

YOLOX 明确检测到 Person，但当前 Face / ReID 证据不足以确认“是谁”。

规则：

```text
保留 Candidate / Track Evidence
显示“检测到人物但身份未确定”
进入异常驱动人工检查
禁止自动创建 Final Character
```

因此：

```text
身份不确定 ≠ 没有人
```

同时也避免重新回到“任何 body detection 都制造一个假人物”的旧问题。

## 模型

固定本地模型：

```text
YuNet
SFace
YOLOX 2022nov
YoutuReID 2021nov
```

正式资产 Run 不允许静默下载模型。

模型必须通过显式 prepare：

```powershell
python -m engine.app.content_models_v2
```

所有文件都校验固定大小和 SHA-256。

缺任一 V4 必需模型：

```text
本次资产 Run = FAILED
旧 Current Analysis / Final Asset 保留
禁止生成“0 人物”的新 AUTO 结果
```

## UI 完整性规则

如果存在 UNRESOLVED Person Evidence，03 资产顶部必须明确显示：

```text
⚠ 人物完整性：N 个 Shot 检测到人物，但身份尚未确定
E01 · SHOT 0006
E01 · SHOT 0012
...
```

这类 Shot 不得静默显示为正常“空人物”。

## Release Gate

单元测试：

```powershell
python -m pytest engine/tests/v2/test_character_models_v4.py -q
python -m pytest engine/tests/v2/test_character_visual_v2.py -q
python -m pytest engine/tests/v2 -q
```

前端：

```powershell
cd frontend
npm run typecheck
npm run build
```

真实短剧回归必须验证：

```text
1. 女主正脸 / 侧脸特写不能漏；
2. 老年人物特写不能漏；
3. 双人镜头必须尽量检测到两个人；
4. 背影 / 遮挡如果身份不能确定，必须出现 UNRESOLVED 提示；
5. 同一演员跨 Shot / 跨 Episode 的碎片数量明显下降；
6. 同一 Shot 的两个人绝不能自动合成一个 Character；
7. 新 Run 失败不能破坏旧 Current / MANUAL Revision。
```

只有真实视频通过以上 Gate，才继续 04「内容剧本」的 Speaker → Final Character 绑定。
