# F05 预览帧并发触发 Alembic KeyError 修复

时间：2026-08-24 16:34 +08:00

## 用户现场错误

F05 页面加载缩略图/关键帧时出现：

```text
render_workbench_frame
→ _project_workspace
→ init_database
→ alembic.command.upgrade
→ EnvironmentContext._remove_proxy
→ KeyError: 'config'
```

## 根因

FastAPI 同步 endpoint 在线程池中执行。F05 页面可能同时请求多个预览帧，而业务层多个函数都会调用 `init_database()`。

旧实现每次 `init_database()` 都执行：

```text
revision check
→ command.upgrade(..., "head")
```

Alembic `EnvironmentContext` 使用进程级代理状态，不支持多个线程同时执行 `command.upgrade()`，因此并发预览请求会破坏其 proxy cleanup，最终出现 `KeyError: 'config'`。

## 修复

`engine/app/core/database.py` 新增：

```text
_DATABASE_INIT_LOCK = threading.RLock()
_INITIALIZED_DATABASE_PATHS: set[Path]
```

正式规则：

```text
当前 Python 进程第一次访问某 app.db
→ 加锁
→ revision / backup / Alembic upgrade
→ 成功后记录 initialized path

后续所有业务请求
→ 命中 initialized cache
→ 直接返回 app.db Path
→ 不再执行 Alembic
```

Migration 失败时不会写入 initialized cache。

开发代码 reload 会产生新 Python 进程，因此新进程仍会重新检查 Migration head，不影响后续 Feature 新增 migration。

## 回归测试

新增：

```text
engine/tests/unit/test_database_concurrency.py
```

覆盖：

1. 16 次调用通过 8 个线程并发首次初始化同一个临时数据库，不得出现 Alembic proxy 异常；
2. 数据库初始化成功后再次调用 `init_database()` 不得重新执行 `command.upgrade()`。

## F05 关键帧缓存规则

`render_workbench_frame()` 继续使用：

```text
<project>/.cache/f05/frames/<source_time_us>.jpg
```

同一 Source 时间 JPEG 已存在且非空时直接返回，不重新运行 FFmpeg。

因此：

```text
镜头边界没变化 + 对应时间帧缓存存在
→ 不重新生成

边界调整 / 拆分 / 合并产生新的关键帧时间点
→ 只生成缺少的新时间点
```

F05 当前仍处于本机回归测试，播放器问题完全通过前不恢复 Stable/Frozen Snapshot。
