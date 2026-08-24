# AI Drama Studio — Project State

> 新对话恢复当前项目状态的第一入口。历史过程放 `docs/sessions/`。

## 当前状态

```text
Project: AI Drama Studio
Official Baseline: main
Current Working Branch: main（用户未要求切换/新建其它分支）
Current Feature: F02 — 上传原视频
Feature Status: READY_FOR_REVIEW
F02 Contract: CONFIRMED
F02 Function Contracts: CONFIRMED
F02 Business Code: COMPLETE
F02 Frontend: COMPLETE
F02 Automated Verification: PASS（见下文限制）
User Acceptance: PENDING
F01 — 创建项目: STABLE / FROZEN
Stable Features: F01
Frozen Features: F01
Next After F02: F03 — 视频预处理（NOT STARTED）
```

`main` 是唯一正式 Source of Truth。未经用户明确要求，不新建/切换/删除/重命名分支，不创建或操作 PR。

---

# F01 冻结基线

权威快照：

```text
docs/features/F01-stable-snapshot.md
```

F02 仅做 Additive 扩展，没有改变 F01 的 Project ID、projects 既有字段语义、project.json V1、Workspace Root、F01 API、creating/ready 或正式 StudioShell UI 基线。

后续任何共享代码修改仍必须回归 F01。

---

# F02 权威文档

```text
docs/features/F02-upload-source-video.md
docs/features/F02-function-contracts.md
docs/features/F02-implementation-log.md
```

其中：

```text
F02-upload-source-video.md
→ Feature 范围 / 数据 / 文件 / API / UI / Recovery / 验收 Contract

F02-function-contracts.md
→ 6 个核心函数 + 2 个 Controller 的详细业务职责

F02-implementation-log.md
→ 当前真实实现、测试结果和用户最终验收步骤
```

用户已经确认 F02 主 Contract、10 项关键设计以及详细函数职责。

---

# F02 已完成能力

完整业务闭环：

```text
项目进入“视频导入”
→ 选择 / 拖拽本地视频
→ 导入前可重新选择
→ multipart 上传到本机 FastAPI
→ 1 MiB 分块写入 staging
→ 同一遍计算 file_size + SHA-256
→ FFprobe 验证真实视频并读取基础媒体信息
→ staging 发布成正式 Source 原片
→ source_videos = ready
→ 页面展示完整 metadata
→ 软件重启后仍可读取
```

F02 不做：

```text
FFmpeg 转码
proxy.mp4
audio.wav
thumbnail.jpg
Source ↔ Proxy mapping
VFR 精确逐帧分析
自动拉片
ASR
人物 / Scene / AI
Source Video 替换 / 删除
多 Source / Episode
```

F03 尚未开始。

---

# F02 Source Contract

```text
1 Project → 0 或 1 个 Source Video
Source ID = SOURCE_<32位UUID4小写hex>
ready 后原片只读，不提供替换/删除
```

Workspace：

```text
<workspace>/
├── project.json
└── source/
    └── SOURCE_<UUID>/
        └── original.<ext>
```

导入中 staging：

```text
<workspace>/source/.staging/SOURCE_<UUID>/original.<ext>
```

数据库只保存相对 Workspace 路径。

原始用户文件名仅保存用于显示/追溯；内部文件名固定为 `original.<安全扩展名>`，视频真实性只相信 FFprobe，不相信扩展名或浏览器 MIME。

---

# Database / Migration

F02 新增：

```text
0002_create_source_videos
source_videos
```

状态：

```text
importing
ready
```

导入后才知道的字段（SHA / size / duration / codec / width / height 等）在 importing 阶段允许 NULL；数据库 CHECK 强制 ready 时核心 metadata 必须完整合法。

## Migration Backup Gate

共享 `init_database()` 已实现：

```text
全新 DB
→ 直接 Alembic → head
→ 不创建无意义 backup

已有 app.db + current revision != head
→ SQLite Connection.backup()
→ <app-data>/backups/app_<UTC>_<old-revision>.db
→ backup 成功后 Alembic upgrade

已有 DB 已是 head
→ 不重复 backup
```

验证：

```text
0001 F01 DB
→ 生成 1 份一致性 backup
→ upgrade 0002
→ F01 Project 数据保留
→ source_videos 建立
→ 再次启动不重复 backup
```

结果：PASS。

---

# F02 6 个核心后端函数 — 全部完成

```text
generate_source_video_id()       DONE
copy_upload_to_staging()         DONE
probe_source_video()             DONE
import_source_video()            DONE
get_source_video()               DONE
recover_source_video_imports()   DONE
```

主要文件：

```text
engine/app/source_videos.py
```

关键行为：

```text
copy_upload_to_staging()
→ 大文件分块写入
→ 不整文件进内存
→ size + SHA-256 同一遍完成

probe_source_video()
→ 原生 FFprobe
→ subprocess 参数数组 / shell=False
→ attached_pic 排除
→ default video/audio stream 优先
→ integer microseconds
→ rational FPS

import_source_video()
→ Project 验证
→ 一项目一原片检查
→ DB importing 恢复锚点
→ staging
→ copy/hash
→ probe
→ final publish
→ DB ready

get_source_video()
→ 读取 ready Source
→ 同时检查正式文件仍存在

recover_source_video_imports()
→ 合法 final + importing：恢复 ready
→ 仅系统明确拥有的 staging：安全清理
→ unknown file / 损坏 final：保留现场，不递归删除
```

---

# F02 API — 全部完成

Additive 新增：

```text
GET  /api/projects/{project_id}/source-video
POST /api/projects/{project_id}/source-video
```

GET：

```text
无 Source → 200 null
ready Source → 200 SourceVideoDTO
```

POST：

```text
multipart/form-data
file = 视频
成功 → 201 Created
```

主要错误：

```text
SOURCE_VIDEO_REQUEST_INVALID
SOURCE_VIDEO_ALREADY_EXISTS
SOURCE_VIDEO_EMPTY
SOURCE_VIDEO_FFPROBE_UNAVAILABLE
SOURCE_VIDEO_PROBE_FAILED
SOURCE_VIDEO_UNSUPPORTED
SOURCE_VIDEO_IMPORT_FAILED
SOURCE_VIDEO_FINALIZATION_PENDING
SOURCE_VIDEO_FILE_MISSING
```

继续使用 F01 冻结 error envelope。

Controller 仍只负责 HTTP → Business → Response，不直接 SQL、写文件、Hash、FFprobe 或 Recovery。

---

# F02 Frontend — 全部完成

新增/修改：

```text
frontend/src/types/source-video.ts
frontend/src/api/source-videos.ts
frontend/src/stores/source-video.ts
frontend/src/views/SourceVideoImport.vue
frontend/src/source-video.css
frontend/src/router/index.ts
frontend/src/components/StudioShell.vue
frontend/src/views/ProjectWorkspace.vue
frontend/src/main.ts
```

已实现：

```text
左侧 02 视频导入正式开放
项目总览“进入视频导入”
系统文件选择
拖拽文件
导入前重新选择
原生 XMLHttpRequest.upload.onprogress
上传百分比 / 已上传字节
100% 后“正在读取媒体信息…”
Ready metadata 展示
SHA-256 完整值 + 复制
重启/刷新重新加载 Source
Ready 后不显示替换/重新上传入口
```

Ready 页面显示：

```text
原文件名
Source ID
文件大小
时长
分辨率
视频编码
FPS + rational
容器格式
音频编码
采样率 / 声道
SHA-256
Workspace 相对路径
```

沿用 F01 用户已验收的深色 StudioShell 和桌面可读字号。

项目流程导航现在明确分开：

```text
01 项目总览
02 视频导入
03 视频预处理（未开放）
04 自动拉片（未开放）
...
```

没有把 F03 视频预处理跳过去。

---

# Dependency

后端新增且固定：

```text
python-multipart==0.0.29
```

没有提前安装：

```text
OpenCV
PyTorch
Whisper
Shot Detection
```

前端没有增加新 npm 包，继续使用现有 package-lock.json。

---

# 自动验证记录

## Backend / F01 Regression + F02

在隔离重建的当前后端工作副本执行：

```text
python -m compileall engine
pytest（F01 regression + F02 core/API）
```

结果：

```text
27 passed
```

覆盖：

```text
F01 create / list / open / recovery / CORS
F02 migration backup
Source ID
chunked streaming
file size / SHA-256
FFprobe JSON 解析
attached_pic 排除
default stream 选择
rational FPS
integer microseconds
import → final → ready
GET Source
第二次导入拒绝
Probe 失败回滚
ready 文件丢失检测
final + importing Recovery
unknown staging file 保护
F02 GET / POST Controller
```

## 真实媒体技术链路

当前执行环境实际使用 FFmpeg 生成测试视频，再走：

```text
真实视频文件
→ multipart
→ staging
→ FFprobe
→ final
→ DB ready
→ GET
```

结果：PASS。

当前工具环境：

```text
FFprobe 7.1.5 (Debian build)
```

这不是用户 Windows 最终环境基线。

## Frontend

新增纯 TypeScript API/Store 已做 TypeScript 语法转译检查：PASS。

当前工具容器没有项目 Vue / Pinia node_modules，无法在这里冒充执行完整：

```text
npm ci
npm run typecheck
npm run build
```

仓库已经有真实 `frontend/package-lock.json`，上述步骤由用户 Windows 工作副本做最终 Gate。

---

# 当前 User Acceptance Gate

F02 代码已经全部完成，当前状态：

```text
READY_FOR_REVIEW
```

但只有用户明确确认实际验收通过，才允许：

```text
F02 → STABLE / FROZEN
```

用户 Windows 最终需要验证：

```text
1. git pull origin main
2. pip install -r engine/requirements.txt
3. ffprobe -version 可正常执行
4. npm ci
5. npm run typecheck
6. npm run build
7. 启动 FastAPI 8080 + Vite
8. 真实短剧原片导入
9. 进度 / metadata / Source 文件位置正确
10. 重启后 Source 仍存在
11. Ready 后不能重复上传覆盖
12. 损坏文件导入失败且不留下 ready Source
13. F01 创建/打开项目仍正常
```

F02 未经用户验收不得进入 F03 正式开发。

---

## 最近更新时间

- 日期：2026-08-24
- 状态：F02 全部规划代码已完成并提交 main；自动后端回归与真实媒体技术链路通过；当前 READY_FOR_REVIEW，等待用户 Windows 真实短剧视频验收。
