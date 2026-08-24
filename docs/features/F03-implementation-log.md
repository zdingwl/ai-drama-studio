# F03 — 视频预处理 Implementation Log

Feature ID: F03  
Implementation Status: CODE COMPLETE  
Review Status: READY_FOR_REVIEW  
Official Baseline: main  
Stable Dependencies: F01、F02 — STABLE / FROZEN

## 1. 已完成代码

### Database / Time Foundation

```text
engine/migrations/versions/0003_create_source_preprocess.py
engine/app/core/media_time.py
```

完成：

- `source_preprocess`；
- `processing / ready`；
- F02→F03 Migration 前 SQLite 一致性 backup；
- processing 阶段不伪造未知媒体 metadata；
- ready 阶段数据库强制 Proxy/Thumbnail/Timeline Mapping 完整；
- ready+Audio 时强制 16kHz/mono/Hash/时长/offset 全部完整；
- Source 无音频时 Audio 字段全部为空；
- 秒/PTS/rational time base ↔ integer microseconds 公共换算；
- Derived ↔ Source offset 映射。

### Backend

```text
engine/app/preprocess.py
engine/app/main.py
```

7 个核心函数全部完成：

```text
generate_proxy_video()
extract_analysis_audio()
generate_thumbnail()
inspect_preprocess_assets()
preprocess_source_video()
get_source_preprocess()
recover_source_preprocesses()
```

2 个 Controller 全部完成：

```text
GET  /api/projects/{project_id}/preprocess
POST /api/projects/{project_id}/preprocess
```

正常链路：

```text
Source size/hash Integrity Gate
→ DB processing
→ preprocess/.staging/SOURCE_xxx/
→ Proxy
→ WAV（有音频时）
→ Thumbnail
→ FFprobe / size / SHA / Profile 校验
→ Source↔Proxy/Audio Mapping
→ staging publish final
→ DB ready
```

失败边界：

- final 发布前失败：只清理本次已知 F03 staging + processing row；
- final 已发布后 DB finalization 失败：不删除派生文件，保留 processing 交给启动 Recovery；
- unknown file / 损坏 final：保留现场；
- F03 任何 Recovery / cleanup 都不得删除 F02 Source。

### Frontend

```text
frontend/src/types/preprocess.ts
frontend/src/api/preprocess.ts
frontend/src/stores/preprocess.ts
frontend/src/views/VideoPreprocess.vue
frontend/src/preprocess.css
frontend/src/router/index.ts
frontend/src/components/StudioShell.vue
frontend/src/views/ProjectWorkspace.vue
frontend/src/main.ts
```

完成：

- `/projects/:projectId/preprocess`；
- 左侧 `03 视频预处理` 正式开放；
- F04 自动拉片仍禁用；
- 无 Source 时阻止并引导 F02；
- Source ready 后显示固定 Profile V1；
- 开始预处理；
- processing 状态不伪造百分比；
- ready 显示 Proxy / Audio / Thumbnail；
- 显示 Source↔Proxy/Audio offset、time base、Source SHA snapshot；
- 无音频时明确显示“不生成静音 WAV”；
- 项目总览根据真实 Source/F03 数据判断当前阶段；
- 8 阶段流程栏布局已修正。

## 2. 固定 F03 Profile V1

Proxy：

```text
H.264 / libx264
CRF 23
preset fast
yuv420p
最大 1280×720
保持比例
不放大小视频
-fps_mode passthrough
有音频时 AAC 128k
faststart
```

Analysis Audio：

```text
PCM s16le
16000 Hz
mono
```

Thumbnail：

```text
min(proxy_duration_us / 10, 5,000,000us)
```

## 3. Timeline Mapping

F03 属于 Source Domain。

```text
source_us = proxy_us + proxy_to_source_offset_us
source_us = audio_us + audio_to_source_offset_us
```

Offset 来自实际 FFprobe stream start timestamp，不假定 Derived 0 == Source 0。

VFR：

- Proxy 不强制 CFR；
- 不允许 F04 使用 `frame_index / fps` 作为唯一 Source 定位；
- 下游必须使用 timestamp + mapping。

## 4. 已实际执行的验证

Foundation：

```text
Media Time targeted tests       6 PASS
0003 Migration/Constraint       3 PASS
0002→backup→0003 upgrade        PASS
```

真实 FFmpeg/FFprobe 7.1.5 技术链路：

```text
1920×1080 + Audio
→ Proxy + 16k mono WAV + Thumbnail + inspect     PASS

No-Audio Source
→ Proxy + Thumbnail / 无假 WAV                   PASS

Source start_time = 2s
→ proxy_to_source_offset_us = 2,000,000          PASS

Synthetic VFR Source
→ Source 有 33/66/100ms 等多种帧间隔
→ Proxy 仍有多种 PTS 间隔                       PASS
```

Python：

```text
preprocess.py + media_time.py py_compile          PASS
```

数据库生命周期约束：

```text
processing + audio target path + NULL metadata   PASS
ready + incomplete Audio metadata                REJECT / PASS
```

## 5. 已加入自动测试

```text
engine/tests/unit/test_database_migration_f03.py
engine/tests/unit/test_media_time_f03.py
engine/tests/unit/test_preprocess_f03.py
engine/tests/unit/test_preprocess_vfr_f03.py
```

覆盖：

- Migration / F01+F02 数据保留；
- processing / ready Constraint；
- integer microseconds / PTS / rational time base；
- Source Integrity mismatch；
- 正常发布；
- 无音频；
- duplicate；
- Recovery final→ready；
- unknown staging file 保护；
- GET/POST API；
- 真实 FFmpeg；
- 非零 Source start；
- VFR cadence。

## 6. 当前执行环境限制

当前工具容器无法联网完整 clone 当前 GitHub 仓库，因此没有声称本轮已经执行完整：

```text
pytest engine/tests 全仓最终回归
npm ci
npm run typecheck
npm run build
```

上述作为用户 Windows 工作副本最终 Review Gate。

这不影响 F03 代码完整性状态，但在用户验收前不得标记 STABLE / FROZEN。

## 7. 用户最终验收

```powershell
cd E:\ai-drama-studio
git pull origin main

.\.venv\Scripts\Activate.ps1
pip install -r engine\requirements.txt
python -m pytest engine\tests -q

cd frontend
npm ci
npm run typecheck
npm run build
npm run dev
```

后端仍按用户当前端口：

```powershell
python -m uvicorn engine.app.main:app --host 127.0.0.1 --port 8080 --reload
```

真实项目重点检查：

1. F02 原片已 ready；
2. 左侧可进入 `03 视频预处理`；
3. 开始后不出现伪造百分比；
4. 完成后 Workspace 有 `preprocess/SOURCE_xxx/proxy.mp4`；
5. 有音频 Source 同目录有 `audio.wav`，且页面显示 16000 Hz / mono；
6. 无音频 Source 不应出现 audio.wav；
7. 有 `thumbnail.jpg`；
8. 页面显示 Proxy / Audio mapping；
9. 原始 `source/SOURCE_xxx/original.ext` 的大小/SHA 不变；
10. 重启应用后 F03 结果仍能读取；
11. 再次预处理被阻止；
12. F01/F02 原有功能仍正常。

用户明确回复“测试通过”或等价结论后，才能创建 F03 Stable Snapshot，并进入 F04。
