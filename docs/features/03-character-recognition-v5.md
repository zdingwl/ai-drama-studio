# 03 资产 · Character Recognition V5

## 目标

人物识别不再以单帧 Observation 为身份单元，而是严格执行：

```text
Final Shot
→ Person Detection
→ Shot 内 Multi-Person Tracking
→ Person Track
→ Track Quality Evaluation
→ Clean Track Gallery
→ Gallery vs Character Gallery
→ Character_ID
→ 持续丰富 Character Gallery
→ Final Shot Character Binding
```

核心验收目标：

1. 画面里有人，不能因为没有脸而静默漏掉。
2. 同一演员不能因为转头、背影、远近景被大量拆成不同 Character。
3. 同一个 Shot 同时出现的两条 Person Track 绝不能绑定到同一个 Character_ID。
4. Character Gallery 正式保存的图片只能包含目标人物本人；多人同框的脏图不得进入正式人物图库。
5. 身份暂时不确定允许保留 UNRESOLVED Track，等待后续 Shot 提供更强 Face/ReID Evidence。
6. YOLOX / YoutuReID 默认 GPU CUDA 优先，失败自动 CPU fallback，并明确显示实际设备。

## 1. Shot 内先数人，再跟 Track

旧版：每个 Shot 抽少量帧，每个 Observation 很快进入跨 Shot 聚类。

V5：Reference Clip 约 6fps 连续采样（极长 Shot 有上限），每帧先跑 YOLOX Person Detection，再用：

- Face/SFace
- YoutuReID
- bbox IoU / 空间连续性
- 最大短暂丢失时间

连接成 Person Track。

Track 表示“一个人在一个 Shot 内的一次连续出现”。短暂遮挡不会立刻切 Track；真正离开或 Shot 结束才结束。

## 2. Track 代表图

每个 Track 的 Observation 计算质量分：

- 人物在画面中的面积
- 清晰度（Laplacian）
- Body 完整度
- Face score / Face area
- Person Detection score
- 其他人物干扰程度

一个 Track 最多保留 6 个有差异的 Representative，避免 6 张几乎相同的照片。

## 3. 多人同框的保存硬规则

正式 Character Gallery 只允许 CLEAN Representative。

CLEAN 要求目标人物 bbox 与同帧其它 Person bbox 的重叠低于门槛；保存图片时再做第二次 crop contamination 检查。

保存顺序：

```text
优先轻微留边 Person Crop
→ 如果留边带入别人，收紧到目标 Person bbox
→ 如果仍有明显其他人物重叠
→ 拒绝进入正式 Character Gallery
```

不采用“把旁边的人模糊掉以后当成干净人物图”的方式，因为被遮挡区域无法可靠恢复目标人物本身。

如果整个 Track 都没有干净帧：

- Track Evidence 仍保留；
- Face/ReID 仍可参与身份判断；
- 不向 Character Gallery 写脏图；
- 如有清晰 Face，可生成 face-only UI cover，但它不计入正式 Gallery。

后续可增加 SAM 2.1 segmentation，进一步提高严重多人场景的隔离能力。

## 4. Track Gallery vs Character Gallery

身份判断不再是一张图对一个平均 embedding，而是多图 Evidence：

- Face Gallery pairwise top-average
- ReID Gallery pairwise top-average
- 前后 Shot 距离
- 同框冲突负证据

判断：

```text
强 Face Match
→ 同一 Character

中等 Face + ReID 支持
→ 同一 Character

无 Face，但相邻 Shot ReID 很强
→ 可挂回已有 Character

证据不足
→ 新建 UNRESOLVED Candidate
```

后续 Track 如果出现 Face 且 ReID 与 UNRESOLVED Candidate 一致，该 Candidate 可以升级为 RESOLVED。

## 5. Character Gallery 持续丰富

每当新的 Track 被确认属于已有 Character_ID：

```text
Track
→ 取 CLEAN Representatives
→ 加入 Character Gallery pool
→ 质量排序 + 多样性去重
→ 保留最多 24 张当前最佳/多样化人物图
```

因此随着 Episode / Shot 分析继续，Character_ID 的图库逐步覆盖：

- 正脸
- 侧脸
- 上半身
- 全身
- 不同姿态
- 不同服装阶段

当前 V5 首先用 embedding 多样性保持差异；后续可再增加显式 front/profile/full-body 分类。

## 6. GPU / CPU 策略

```text
YOLOX Person Detection → ONNX Runtime CUDA 优先 → CPU fallback
YoutuReID              → ONNX Runtime CUDA 优先 → CPU fallback
YuNet / SFace          → OpenCV CPU
Track / Gallery Match  → CPU
```

页面必须显示实际 runtime：

- `GPU · CUDA · CUDAExecutionProvider`
- 或 `CPU fallback · CPUExecutionProvider`

禁止静默降级。

## 7. 数据与 Final Asset 关系

V5 仍保持：

```text
Observation / Track / Gallery = AI Evidence
Character Candidate           = AI Identity Evidence
Final Character               = 可编辑 Source of Truth
Shot Character Binding        = 最终业务绑定
```

UNRESOLVED body-only Candidate 不自动升级 Final Character。

## 8. 当前代码

- `engine/app/character_visual_v5.py`：V5 正式人物链。
- `engine/app/character_visual_v2.py`：兼容入口，已经路由到 V5。
- `engine/app/character_visual_gpu_v41.py`：GPU-first YOLOX / ReID runtime wrapper，V5 复用。
- `engine/app/inference_runtime_v41.py`：CUDA 优先 / CPU fallback。
- `engine/app/asset_analysis_progress_v4.py`：正式资产 Task 进度，已显示 V5 Track / Gallery 阶段。
- `engine/tests/v2/test_character_visual_v2.py`：历史身份规则回归。
- `engine/tests/v2/test_character_visual_v5.py`：V5 Track / Clean Gallery 回归。

## 9. 本机 Release Gate

```powershell
cd D:\ai-drama-studio
git pull
.\.venv\Scripts\Activate.ps1

python -m pytest engine/tests/v2/test_character_visual_v2.py -q
python -m pytest engine/tests/v2/test_character_visual_v5.py -q
python -m pytest engine/tests/v2/test_character_models_v4.py -q
python -m pytest engine/tests/v2/test_asset_progress_v4.py -q
python -m pytest engine/tests/v2 -q

cd frontend
npm run typecheck
npm run build
```

真实视频必须重点回归：

- 单人大特写
- 双人同框
- 前后遮挡
- 背影 / 侧脸
- 人物离开后重新进入
- 同演员换姿态 / 远近景
- 多人同框 Character Gallery 是否只保存目标人物本人

单元测试通过不等于真实人物识别验收通过。
