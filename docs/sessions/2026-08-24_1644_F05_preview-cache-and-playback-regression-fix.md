# F05 预览缓存 / 播放并发回归修复

时间：2026-08-24 16:44 +08:00  
分支：main

## 用户真实反馈

F05 Final Shots 已确认后，用户继续发现：

```text
1. 视频一度不能播放
2. 关键帧不应每次打开重新生成
3. 播放过程中当前 Shot 关键帧也应该继续出现
4. 后端出现 Alembic KeyError: 'config'
```

## 根因与修复

### Alembic 并发

多个 frame 请求进入 FastAPI thread pool 后同时调用 `init_database()`，导致 Alembic `EnvironmentContext` 进程级代理并发冲突。

修复：

```text
engine/app/core/database.py
→ RLock
→ initialized database path set
→ 每数据库每进程只 Migration 一次
```

测试：

```text
engine/tests/unit/test_database_concurrency.py
```

### 预览调度

最终调度策略：

```text
Proxy metadata 最优先
当前 Shot 5 关键帧：高优先级；播放中也允许；串行
整集 Shot 缩略图：低优先级；播放中暂停；暂停后继续
```

### 磁盘缓存

```text
.cache/f05/frames/<source_time_us>.jpg
```

如果文件存在且非空，`render_workbench_frame()` 直接返回，禁止再次启动 FFmpeg。

新增测试：

```text
test_render_workbench_frame_reuses_existing_cache_without_ffmpeg
```

### 浏览器缓存

`GET /shot-workbench/frame` 现在返回：

```text
Cache-Control: private, max-age=31536000, immutable
```

同一 Project + Source 时间 URL 内容稳定时，刷新/重新打开页面允许浏览器直接复用。

## Freeze 状态

用户虽然已经把真实项目 Final Shots 确认为 `confirmed`，但这只是业务数据锁定。

由于确认后发现播放/预览回归：

```text
F05 Feature = NOT FROZEN
```

此前短暂创建的 `F05-stable-snapshot.md` 已删除。

最终回归通过后再重新创建 F05 Stable Snapshot。
