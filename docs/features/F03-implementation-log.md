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
→ 再次核验 Source size/SHA 未在处理中变化
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

媒体时长语义：

```text
优先选中 video/audio stream.duration
→ 缺失时才回退 format.duration
```

原因：容器中音频尾巴可能比视频稍长，F04 的 Proxy 视频时长不能被更长的容器音频错误扩大。

## 4. 验收前代码审查与真实验收修复

### 4.1 Source 处理中变化保护

现在流程固定：

```text
开始前核验 F02 size + SHA
→ 建立 source_sha256_snapshot
→ 生成/inspect Proxy/WAV/Thumbnail
→ publish 前再次核验 F02 size + SHA + 本次 snapshot
→ 一致才允许 publish
```

处理中发生变化：

```text
SOURCE_VIDEO_INTEGRITY_MISMATCH
→ 不发布 final
→ 清理本次已知 staging
→ 删除 processing row
→ 不修改 F02 Source 记录
```

### 4.2 Stream Duration 优先

固定为：

```text
stream.duration
→ 缺失时 format.duration
```

Video / Audio 都以当前选中流自身时长为第一权威。

### 4.3 processing 残留允许安全重试

用户实际验收时出现：

```text
页面 GET 无 ready 结果
→ 用户看到“开始视频预处理”
→ POST 发现 DB 已有旧 processing
→ 原实现统一报“当前项目已经存在视频预处理记录”
```

这是 F03 重试逻辑缺口。现在 `preprocess_source_video()` 对旧 `processing` 做当前项目定向安全恢复：

```text
已有 ready
→ PREPROCESS_ALREADY_EXISTS（继续保持禁止重复预处理）

已有 processing
→ final 完整且可校验
   → 自动恢复 ready，并返回恢复后的结果

→ staging 最近 30 秒仍有系统文件写入
   → PREPROCESS_IN_PROGRESS
   → 不删除，避免误伤仍在运行的 FFmpeg

→ staging 已停止写入且只包含 proxy/audio/thumbnail 等系统已知文件
   → 安全清理旧 staging + processing row
   → 本次点击继续重新预处理

→ 没有 staging/final 且 processing 记录已超过保护窗口
   → 删除旧 processing row
   → 本次点击继续重新预处理

→ 有未知文件、异常 final、Source Hash 不一致
   → PREPROCESS_RECOVERY_REQUIRED
   → 保留现场，不自动删除
```

HTTP 层新增稳定 409 映射：

```text
PREPROCESS_IN_PROGRESS
PREPROCESS_RECOVERY_REQUIRED
```

F02 Source 原片在任何上述路径中都不会被删除或覆盖。

## 5. 已实际执行的开发阶段验证

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

数据库生命周期约束：

```text
processing + audio target path + NULL metadata   PASS
ready + incomplete Audio metadata                REJECT / PASS
```

说明：最新 processing 重试恢复测试已经写入仓库；当前工具环境无法完整 clone 最新仓库，因此不虚构本轮新增测试的执行结果，仍以用户 Windows 全量 pytest 作为最终 Gate。

## 6. 已加入自动测试

```text
engine/tests/unit/test_database_migration_f03.py
engine/tests/unit/test_media_time_f03.py
engine/tests/unit/test_preprocess_f03.py
engine/tests/unit/test_preprocess_vfr_f03.py
engine/tests/unit/test_preprocess_integrity_f03.py
engine/tests/unit/test_preprocess_retry_recovery_f03.py
```

新增重试覆盖：

```text
旧 processing + 无文件 → 自动清理并重新处理
最近仍在写 staging → PREPROCESS_IN_PROGRESS，不删除文件
未知 staging 文件 → PREPROCESS_RECOVERY_REQUIRED，保留现场
ready 后再次预处理 → 继续 PREPROCESS_ALREADY_EXISTS
```

## 7. 当前执行环境限制

当前工具容器无法联网完整 clone 当前 GitHub 仓库，因此没有声称本轮已经执行完整：

```text
pytest engine/tests 全仓最终回归
npm ci
npm run typecheck
npm run build
```

上述作为用户 Windows 工作副本最终 Review Gate。

F03 在用户验收前不得标记 STABLE / FROZEN。

## 8. 用户最终验收

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

后端：

```powershell
python -m uvicorn engine.app.main:app --host 127.0.0.1 --port 8080 --reload
```

真实项目重点检查：

1. F02 原片已 ready；
2. 左侧可进入 `03 视频预处理`；
3. 遗留旧 `processing` 时再次点击可以安全恢复/清理并继续；
4. 开始后不出现伪造百分比；
5. 完成后 Workspace 有 `preprocess/SOURCE_xxx/proxy.mp4`；
6. 有音频 Source 同目录有 `audio.wav`，且页面显示 16000 Hz / mono；
7. 无音频 Source 不应出现 audio.wav；
8. 有 `thumbnail.jpg`；
9. 页面显示 Proxy / Audio mapping；
10. 原始 `source/SOURCE_xxx/original.ext` 的大小/SHA 不变；
11. 重启应用后 F03 结果仍能读取；
12. ready 后再次预处理被阻止；
13. F01/F02 原有功能仍正常。

用户明确回复“测试通过”或等价结论后，才能创建 F03 Stable Snapshot，并进入 F04。
