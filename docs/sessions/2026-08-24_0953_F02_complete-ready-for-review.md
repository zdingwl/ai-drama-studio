# F02 上传原视频 — 完整开发交接

日期：2026-08-24  
分支：main（用户未要求新建/切换其它分支）

## 用户要求

用户明确要求：

```text
完成整个 F02 开发
```

因此本轮不再按单函数停顿，而是完成 F02 全部后端、API、前端、测试与文档收尾，但仍严格禁止进入 F03。

## 当前结论

```text
F01 = STABLE / FROZEN
F02 = READY_FOR_REVIEW
F03 = NOT STARTED
```

F02 业务代码已经完整提交 `main`；只有用户 Windows 真实原片验收通过后才能标记 `STABLE / FROZEN`。

## 已完成后端

```text
engine/app/source_videos.py
```

6 个核心函数：

```text
generate_source_video_id()
copy_upload_to_staging()
probe_source_video()
import_source_video()
get_source_video()
recover_source_video_imports()
```

完成：

- Source ID；
- 1 MiB chunked upload；
- size + SHA-256 单遍计算；
- FFprobe 基础媒体真实性验证；
- attached_pic 排除；
- default video/audio stream 选择；
- duration/start_time → integer microseconds；
- FPS rational；
- staging → final；
- importing → ready；
- final 发布后禁止自动删除；
- interrupted import Recovery；
- unknown user file 保护；
- DB ready 但原片丢失时显式报错。

## API

```text
GET  /api/projects/{project_id}/source-video
POST /api/projects/{project_id}/source-video
```

POST 使用 multipart/form-data + UploadFile。

Controller 不直接 SQL、不写文件、不算 Hash、不运行 FFprobe。

## Migration

```text
0002_create_source_videos
```

已有 F01 `app.db` 在有 pending migration 时：

```text
SQLite Connection.backup()
→ backups/
→ Alembic upgrade
```

已是最新 head 时不重复备份。

## Frontend

新增：

```text
frontend/src/types/source-video.ts
frontend/src/api/source-videos.ts
frontend/src/stores/source-video.ts
frontend/src/views/SourceVideoImport.vue
frontend/src/source-video.css
```

更新：

```text
frontend/src/router/index.ts
frontend/src/components/StudioShell.vue
frontend/src/views/ProjectWorkspace.vue
frontend/src/main.ts
```

功能：

- 左侧 F02 视频导入入口；
- 拖拽 / 系统文件选择；
- 正式导入前重新选择；
- 上传进度百分比；
- 上传字节 / 总字节；
- 上传 100% 后 FFprobe processing 状态；
- Ready metadata 展示；
- SHA-256 复制；
- Ready 后禁止第二次上传/替换；
- 刷新/重启重新读取 Source。

## Dependency

新增：

```text
python-multipart==0.0.29
```

未引入 F03 以后 AI/视频分析依赖。

## 自动验证

隔离重建当前后端工作副本：

```text
python -m compileall engine
F01 regression + F02 core/API pytest
```

结果：

```text
27 passed
```

另外：

```text
0001 → backup → 0002 migration regression = PASS
```

实际媒体技术链路：

```text
真实生成测试视频
→ multipart
→ staging
→ FFprobe
→ final
→ DB ready
→ GET
```

结果：PASS。

工具环境 FFprobe 为 7.1.5 Debian build；这不是用户最终 Windows FFprobe baseline。

前端新增纯 TS API/Store 已做 TypeScript 语法检查；完整 `npm ci / vue-tsc / vite build` 由用户 Windows 最终执行。

## 用户最终验收

```text
git pull origin main
pip install -r engine/requirements.txt
ffprobe -version
npm ci
npm run typecheck
npm run build
```

启动：

```text
FastAPI: 127.0.0.1:8080
Vite: localhost:5173 或自动备用端口
```

真实短剧验收：

1. F01 项目进入“视频导入”；
2. 选择真实 MP4/MOV/MKV；
3. 正式导入前可重新选择；
4. 开始导入有进度；
5. 100% 后显示读取媒体信息；
6. Ready 后 metadata 正确；
7. Workspace 存在 `source/SOURCE_xxx/original.ext`；
8. 不产生 F03 的 proxy/wav/thumbnail；
9. 重启应用后仍能显示 Source；
10. Ready 后不能覆盖原片；
11. 损坏视频不能留下 ready Source；
12. F01 创建/打开项目回归正常。

用户明确确认后：

```text
F02 → STABLE / FROZEN
```

然后才能规划/开发 F03。
