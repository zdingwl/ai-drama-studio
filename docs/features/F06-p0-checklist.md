# F06 — P0 Feature Checklist

Feature: F06 自动人物识别  
Status: PLANNED / CONTRACT CONFIRMED  
Upstream: F05 STABLE / FROZEN

> 这是编码前检查表。当前阶段只允许标记“设计已定义 / 编码前待验证”；只有真实开发和测试完成后才能把 Stable Gate 改成 PASS。

---

## P0-01 Dependency / Revision / Invalidation

- 适用：Yes
- 原因：F06 是从 F05 Final Shot 派生出的自动人物 Evidence。
- 上游依赖：

```text
shot_edit_sets.id
shot_edit_sets.revision
shot_edit_sets.status = confirmed
final_shots.id
final_shots.final_start_us / final_end_us
```

- 本 Feature 产生：

```text
character_detection_runs
character_candidates
character_tracks
```

- 上游变化：F05 Frozen Contract 下 confirmed 后不再允许边界修改，因此正常路径不会变化；若未来 Change Request / Migration 产生新的 Final Shot revision，则旧 F06 Run 必须 stale，不允许静默继续作为 F07 输入。
- stale UI：显示来源 revision 不一致并禁止进入新建 F07 Final Character。
- 重新计算：显式 `rerun_character_detection()`。
- 人工 override：F06 不允许修改自动 Evidence；人工修正属于 F07。

开发完成：`PENDING`

---

## P0-02 Media Timebase

- 适用：Yes
- 原因：人物 Evidence 必须精确绑定 Final Shot 和 Source Timeline。
- 输入 timeline：Source Timeline / F05 Final Shot。
- 输出 timeline：Source Timeline Evidence time。
- 权威单位：integer microseconds。
- Source↔Proxy：需要；抽帧时使用 F05/F03 已冻结映射语义。
- VFR：需要兼容；禁止 frame index / fps 作为正式时间。
- 音频 sample rate：N/A，F06 不读音频。
- rounding：采样数量使用明确 round-half-up；Source time 全程整数微秒。
- 时间误差测试：至少覆盖非整数 FPS/VFR Proxy、短 Shot、首尾 Shot、边界避让。

开发完成：`PENDING`

---

## P0-03 Environment Baseline

- 适用：Yes
- 新增 Python 依赖计划：

```text
opencv-python==4.11.0.86
```

- 复用：

```text
numpy==2.1.3
FFmpeg / FFprobe
```

- 新增本地模型：

```text
YuNet face_detection_yunet_2023mar.onnx
SFace face_recognition_sface_2021dec.onnx
```

- 模型来源：OpenCV Zoo。
- 模型 SHA-256：`PENDING`；编码开始前必须实际下载固定文件、计算 SHA-256 并写入 `config/models.yaml`。
- 运行设备：V1 固定 OpenCV CPU DNN。
- 对现有 PyTorch/CUDA：不得升级/替换；F04 已冻结的 `torch 2.5.1+cu124` 不属于 F06 变更范围。
- 当前本机：NVIDIA GeForce RTX 3060 Ti；F06 V1 不依赖 GPU 显存。
- 新电脑安装：requirements + models manifest + model download/checksum verify。
- 安装验证计划：

```text
python -c "import cv2; print(cv2.__version__); print(hasattr(cv2, 'FaceDetectorYN')); print(hasattr(cv2, 'FaceRecognizerSF'))"
```

开发完成：`PENDING`

---

## P0-04 DB + File Recovery

- 适用：Yes
- DB transaction：

```text
processing Run 可先落库
→ 算法完成
→ Candidate / Track 写入 staging transaction
→ validate
→ 同一事务 old is_current=0 + new ready/is_current=1
```

- 文件：只写 `.cache/f06/` UI/分析缓存，不是正式业务资产。
- staging/tmp：新抽帧/face crop 先 `.tmp`，写完/可读后 atomic rename。
- 文件校验：JPEG 非空且 OpenCV 可 decode。
- 崩溃：processing Run 可在重启时识别为 interrupted/failed；不得覆盖旧 Current Ready Run。
- restart recovery：旧 current 继续可用；未完成的新 Run 可标记 failed 后允许显式重跑。
- Migration：计划 `0007_create_character_detection`。
- Migration backup：沿用项目统一 migration backup 规则。
- orphan cache：允许清理并按 Source time + bbox 重建。
- missing model：Run 失败为明确 `CHARACTER_MODEL_UNAVAILABLE` / `MODEL_HASH_MISMATCH`，不得随机初始化。

开发完成：`PENDING`

---

## P0-05 Provider Job Safety

- 适用：No
- 原因：F06 全本地 OpenCV 推理，无付费/异步 Provider，不存在重复扣费风险。
- Provider：N/A
- local_job_id：N/A
- request_fingerprint：N/A
- idempotency：本地 Run 通过数据库状态控制，不属于 Provider safety。
- provider_task_id：N/A
- submit timeout：N/A
- poll retry：N/A
- restart resume：由 P0-04 本地 Run Recovery 处理。
- cost：N/A

开发完成：`N/A`

---

# Stable Gate

当前规划阶段：

```text
P0 DEPENDENCY REVIEW: PENDING IMPLEMENTATION
P0 TIMEBASE REVIEW: PENDING IMPLEMENTATION
P0 ENVIRONMENT REVIEW: PENDING MODEL HASH / WINDOWS SMOKE TEST
P0 RECOVERY REVIEW: PENDING IMPLEMENTATION
P0 PROVIDER JOB REVIEW: N/A
```

编码前必须先完成：

```text
1. 固定 opencv-python 版本进入 requirements
2. 固定 YuNet / SFace model manifest + SHA-256
3. Windows 本机确认 FaceDetectorYN / FaceRecognizerSF 可创建模型
4. 再开始 F06 业务代码
```

任一适用项未 PASS，F06 不得 STABLE / FROZEN。
