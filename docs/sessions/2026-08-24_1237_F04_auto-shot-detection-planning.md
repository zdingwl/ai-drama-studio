# Session — F04 自动拉片规划

时间：2026-08-24 12:37 +08:00  
Branch：main  
状态：PLANNED / WAITING_USER_CONFIRMATION

## 用户指令

```text
开始F04「自动拉片」
```

## 本次完成

已读取并遵守：

```text
AGENTS.md
SKILL.md
docs/PROJECT_STATE.md
docs/FEATURE_SEQUENCE.md
docs/features/F03-stable-snapshot.md
templates/P0_FEATURE_CHECKLIST.md
```

已新增：

```text
docs/features/F04-auto-shot-detection.md
docs/features/F04-function-contracts.md
```

已更新：

```text
docs/PROJECT_STATE.md
```

## 关键设计

F04 V1：

```text
F03 ready proxy.mp4
→ FFmpeg scdet
→ 真实 PTS Cut Event
→ 120ms 去抖
→ Proxy→Source offset 映射
→ 连续 Shot Candidate
→ DB ready
```

固定 Detector Profile：

```text
ffmpeg_scdet
profile_version = 1
threshold = 10.0
min_boundary_gap_us = 120000
```

不新增 Python / Node / 云 Provider。

自动结果与人工 Final 分离：

```text
F04 = detected_* evidence
F05 = final human shots
```

F04 不实现边界拖动、拆分、合并、新增、删除。

## Planned Database

```text
0005_create_shot_detection
shot_detection_runs
shot_candidates
```

Candidate 同时保存：

```text
Proxy Timeline integer microseconds
Source Timeline integer microseconds
```

VFR 只按 PTS 定位，不使用 frame_index / fps 作为权威时间。

## Planned Core Functions

```text
generate_shot_detection_id()
detect_proxy_cut_events()
build_shot_candidates()
run_shot_detection()
get_shot_detection()
recover_shot_detections()
```

Controller：

```text
get_shot_detection_api()
run_shot_detection_api()
```

## 当前 Gate

```text
F01 STABLE / FROZEN
F02 STABLE / FROZEN
F03 STABLE / FROZEN
F04 PLANNED / WAITING_USER_CONFIRMATION
F05 NOT STARTED
```

没有业务编码，没有新建/切换分支，没有开始 F05。

用户确认 F04 规划后，下一步：

```text
F04 → IN_PROGRESS
→ 0005 Migration
→ SCDet / PTS parser
→ Candidate builder
→ Detection service + Recovery
→ API
→ Vue
→ regression / real sample
```
