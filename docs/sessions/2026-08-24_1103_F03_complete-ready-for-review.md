# F03 完整开发完成，进入 READY_FOR_REVIEW

时间：2026-08-24 11:03 +08:00  
分支：main（用户未要求新建/切换分支）

## 用户指令

用户明确要求：

```text
直接完成F03 的全部开发
```

因此本轮一次完成 F03 后端核心、API、Recovery、Vue 页面、自动测试文件和媒体技术验证，但没有进入 F04。

## 完成内容

### Backend

```text
engine/app/preprocess.py
```

7 个核心函数：

```text
generate_proxy_video()
extract_analysis_audio()
generate_thumbnail()
inspect_preprocess_assets()
preprocess_source_video()
get_source_preprocess()
recover_source_preprocesses()
```

### API

`engine/app/main.py` Additive 新增：

```text
GET  /api/projects/{project_id}/preprocess
POST /api/projects/{project_id}/preprocess
```

启动 Recovery 顺序：

```text
F01 Project
→ F02 Source
→ F03 Preprocess
```

### Database

```text
0003_create_source_preprocess
source_preprocess
```

开发收尾发现并修复：processing 阶段有音频 Source 会先保存 `audio.wav` 目标路径，此时 size/hash/duration 尚未生成；Audio 完整性 CHECK 必须只在 ready 阶段强制，否则合法 processing row 无法创建。

### Timebase

公共：

```text
engine/app/core/media_time.py
```

F03 保存实际 stream start timestamp 推导的 Proxy/Audio→Source offset；不默认 Proxy 0 = Source 0。

### Frontend

新增：

```text
frontend/src/types/preprocess.ts
frontend/src/api/preprocess.ts
frontend/src/stores/preprocess.ts
frontend/src/views/VideoPreprocess.vue
frontend/src/preprocess.css
```

更新：

```text
frontend/src/router/index.ts
frontend/src/components/StudioShell.vue
frontend/src/views/ProjectWorkspace.vue
frontend/src/main.ts
```

左侧 `03 视频预处理` 已开放；`04 自动拉片` 保持禁用。

## 媒体技术验证

在当前工具容器使用 FFmpeg/FFprobe 7.1.5 实际验证：

```text
1080p + Audio → Proxy/WAV/Thumbnail                 PASS
No Audio → Proxy/Thumbnail，无 fake WAV            PASS
Source start_time=2s → proxy offset=2,000,000us    PASS
Synthetic VFR → Proxy 仍保留多种 frame PTS delta  PASS
```

VFR 样本 Source/Proxy 都保留约 33ms、66ms 等不同帧间隔，没有被 `-fps_mode passthrough` 强制为单一 CFR。

## 自动测试文件

```text
engine/tests/unit/test_database_migration_f03.py
engine/tests/unit/test_media_time_f03.py
engine/tests/unit/test_preprocess_f03.py
engine/tests/unit/test_preprocess_vfr_f03.py
```

当前容器因网络限制不能完整 clone 当前 GitHub 仓库，所以未声称完成全仓 pytest 或 npm build。用户 Windows 最终验收必须执行：

```text
python -m pytest engine/tests -q
npm ci
npm run typecheck
npm run build
```

## 当前状态

```text
F01 STABLE / FROZEN
F02 STABLE / FROZEN
F03 READY_FOR_REVIEW
F03 User Acceptance PENDING
F04 NOT STARTED
```

只有用户明确确认 F03 实际测试通过，才能创建 F03 Stable/Frozen Snapshot 并开始 F04。
