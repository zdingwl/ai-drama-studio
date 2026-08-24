# F02 — 上传原视频：Implementation Log

Feature ID: F02  
Implementation Status: CODE COMPLETE  
Review Status: READY_FOR_REVIEW  
Official Baseline: main  
Stable Dependency: F01 — STABLE / FROZEN

## 已完成代码

### Database / Migration

```text
engine/app/core/database.py
engine/migrations/versions/0002_create_source_videos.py
```

完成：

- `source_videos` 表；
- `importing / ready`；
- ready metadata 数据库 CHECK；
- F01 `app.db` 从旧 Revision 升级前使用 SQLite `Connection.backup()` 产生一致性备份；
- 已是 head 时不重复备份；
- F01 `projects` 冻结字段不变。

### Backend

```text
engine/app/source_videos.py
engine/app/main.py
```

6 个核心函数全部完成：

```text
generate_source_video_id()
copy_upload_to_staging()
probe_source_video()
import_source_video()
get_source_video()
recover_source_video_imports()
```

2 个 Controller 全部完成：

```text
GET  /api/projects/{project_id}/source-video
POST /api/projects/{project_id}/source-video
```

行为：

```text
multipart UploadFile
→ 1 MiB chunk 流式写 staging
→ 同时计算 size + SHA-256
→ FFprobe 校验/读取 metadata
→ staging 目录同盘发布 final
→ DB ready
```

失败：

- final 发布前失败：只清理本次 Source 的 staging + importing row；
- final 已发布后 DB 最终提交失败：不删除原片，保留 importing，由启动 Recovery 补全；
- unknown file 不递归删除；
- ready Source 不覆盖、不替换、不删除。

### Frontend

```text
frontend/src/types/source-video.ts
frontend/src/api/source-videos.ts
frontend/src/stores/source-video.ts
frontend/src/views/SourceVideoImport.vue
frontend/src/source-video.css
frontend/src/router/index.ts
frontend/src/components/StudioShell.vue
frontend/src/views/ProjectWorkspace.vue
```

完成：

- 左侧 `02 视频导入` 正式开放；
- 项目总览可进入 F02；
- 拖拽 / 系统文件选择；
- 导入前重新选择；
- 原生 `XMLHttpRequest.upload.onprogress` 上传进度；
- 100% 后显示“正在读取媒体信息”；
- Ready 后显示：文件名、大小、时长、分辨率、视频编码、FPS、容器、音频编码、采样率/声道、SHA-256、Workspace 相对路径；
- SHA-256 可复制；
- Ready 后不提供第二次上传/替换入口；
- 页面沿用 F01 已验收深色 StudioShell 和桌面可读字号。

### Dependency

```text
python-multipart==0.0.29
```

没有提前安装 OpenCV / PyTorch / Whisper 等 F03+ 依赖。

## 自动验证结果

本次在隔离重建的当前后端工作副本执行：

```text
python -m compileall engine
pytest: F01 regression + F02 core/API
```

结果：

```text
27 passed
```

覆盖：

```text
F01 create/open/list/recovery/CORS
F02 chunked copy
size / SHA-256
FFprobe JSON 解析
attached_pic 排除
default stream 选择
rational FPS / integer microseconds
import → ready
GET Source
第二次导入拒绝
Probe 失败回滚
ready 文件缺失检测
final+importing Recovery
unknown staging file 保护
F02 GET/POST HTTP Controller
```

另外单独重跑 Migration Upgrade 场景：

```text
0001 DB + F01 Project
→ 生成 1 份 SQLite backup
→ upgrade 0002
→ F01 Project 数据仍存在
→ source_videos 存在
→ 第二次 init 不重复 backup
```

结果：`PASS`。

媒体工具验证环境（不是用户 Windows 最终基线）：

```text
FFprobe 7.1.5 (Debian build)
FFmpeg  7.1.5 (仅用于自动生成测试视频)
```

在该环境还执行过真实媒体字节链路：测试视频 → multipart → staging → FFprobe → final → ready → GET，结果通过。

前端：新增 TypeScript API/Store 代码已做 TypeScript 语法转译检查，`PASS`。当前执行容器没有项目 Vue/Pinia node_modules，因此最终 `vue-tsc + vite build` 仍由用户 Windows 工作副本执行。

## 用户最终验收步骤

用户本地更新：

```powershell
cd E:\ai-drama-studio
git pull origin main
```

后端依赖：

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r engine\requirements.txt
```

确认 FFprobe：

```powershell
ffprobe -version
```

启动后端：

```powershell
python -m uvicorn engine.app.main:app --host 127.0.0.1 --port 8080 --reload
```

前端：

```powershell
cd frontend
npm ci
npm run typecheck
npm run build
npm run dev
```

真实短剧验收：

```text
1. 打开一个 F01 项目
2. 左侧进入“视频导入”
3. 选择真实 MP4/MOV/MKV 原片
4. 导入前测试“重新选择”
5. 开始导入，观察进度
6. 上传 100% 后观察“读取媒体信息”
7. Ready 后核对大小/时长/分辨率/编码/FPS/音频/SHA/path
8. 确认 Workspace 只有 source/SOURCE_xxx/original.ext，没有 F03 proxy/wav/thumbnail
9. 重启前后端，再进入视频导入页，Source 仍存在
10. 确认页面不再提供替换原片入口
11. 新建另一个项目，上传损坏文件，必须失败且不留下 ready Source
12. 回归 F01 新建/打开项目仍正常
```

只有用户明确确认通过后：

```text
F02 → STABLE / FROZEN
```

当前禁止进入 F03 正式开发。
