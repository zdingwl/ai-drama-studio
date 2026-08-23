# F02 上传原视频 — Contract Planning Handoff

时间：2026-08-23 22:39 +08:00  
分支：main（未创建新分支）

## 触发

F01 已由用户验收并正式 STABLE / FROZEN。

用户随后明确说：

```text
开始
```

根据上一轮约定，本次“开始”解释为：进入 F02「上传原视频」详细规划，不直接跳过 Contract 开码。

## 已完成

新增：

```text
docs/features/F02-upload-source-video.md
```

更新：

```text
docs/PROJECT_STATE.md
```

当前：

```text
Current Feature = F02 — 上传原视频
Feature Status = PLANNED
F02 Contract = DRAFTED / WAITING_USER_CONFIRMATION
Business Code = NOT STARTED
```

## F02 核心边界

```text
只做：
原片导入 + Source Asset + FFprobe 基础 metadata + 重启持久化

不做：
转码 / proxy / WAV / thumbnail / VFR 精确分析 / 自动拉片 / ASR / AI
```

F03 仍是视频预处理。

## 关键 Draft

```text
Source ID = SOURCE_<UUID4_HEX>
1 Project → 0/1 ready Source Video
ready Source 只读
原片复制进 Workspace
source/SOURCE_<id>/original.<ext>
staging = source/.staging/SOURCE_<id>/original.<ext>
```

DB Draft：

```text
0002_create_source_videos
source_videos
```

API Draft：

```text
GET  /api/projects/{project_id}/source-video
POST /api/projects/{project_id}/source-video
```

## 核心函数

只保留 6 个真正重要的函数：

```text
generate_source_video_id()
copy_upload_to_staging()
probe_source_video()
import_source_video()
get_source_video()
recover_source_video_imports()
```

简单 helper / 格式化函数不单独做大篇 Contract。

## 文件安全

```text
DB importing
→ chunk streaming + sha256
→ FFprobe
→ publish final
→ DB ready
```

Final 未发布失败可清理本 Source staging。
Final 已发布但 DB ready 失败必须保留原片，Recovery 完成状态。
Ready Source 永不自动覆盖/删除。

## P0-04 Migration Safety

F02 首次增加 0002 Migration，因此不能直接让现有 F01 `init_database()` 无备份升级。

编码前必须增加最小安全 Gate：

```text
existing app.db + pending migration
→ SQLite safe backup
→ app-data/backups/
→ Alembic upgrade
```

共享数据库初始化内部实现变化必须跑完整 F01 Regression。

## Environment

F02 首次使用 Native FFprobe。

目标 Windows 编码/验收要记录：

```text
ffprobe -version
```

更新 Environment Baseline。

F02 Python 只计划增加 multipart 上传所需依赖；不提前装 OpenCV/PyTorch/Whisper。

## 等待用户确认

10 项关键设计已写入 F02 Contract / PROJECT_STATE。

用户若回复：

```text
确认
可以
按这个开发
开始开发
```

且没有提出修改，则：

```text
F02 → IN_PROGRESS
```

直接在 main 开发，不新建分支。

开发顺序：

```text
Migration Backup Gate
→ Source ID
→ streaming copy
→ FFprobe
→ import/get/recovery
→ API
→ Vue 视频导入页
→ Tests + F01 Regression
→ 真实短剧视频测试
```

不要进入 F03，直到 F02 用户验收并 FROZEN。
