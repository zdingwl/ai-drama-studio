# 2026-08-24 17:04 — F05 Final Regression / Freeze

## 用户最终确认

用户在 Windows 本机真实项目中完成 F05 最终回归并明确回复“确认”。

页面真实状态：

```text
31 SHOTS
FINAL SHOTS CONFIRMED
Proxy 视频可正常播放
当前 Shot 可随播放切换
左侧缩略图正常
```

## 本轮最终冻结前修复

1. 左侧 Shot 缩略图破图：改为队列加载、失败重试、取镜头中间位置。
2. 当前 Shot 跟随：播放跨 Shot 自动高亮，左侧自动滚动并保留上下可视空间。
3. 播放器与 FFmpeg 预览抢资源：Proxy 优先；当前 Shot 5 关键帧播放中串行；整集缩略图播放中暂停。
4. Alembic `KeyError: 'config'`：`init_database()` 增加进程级 RLock 和 database-path initialized cache，同进程只执行一次 Migration。
5. 关键帧缓存：`.cache/f05/frames/<source_time_us>.jpg` 命中后禁止再次调用 FFmpeg；HTTP 长期缓存。
6. 新增并发与缓存复用回归测试。

## 冻结结果

```text
F05 = STABLE / FROZEN
```

新建：

```text
docs/features/F05-stable-snapshot.md
```

同步：

```text
docs/features/F05-shot-workbench.md
docs/PROJECT_STATE.md
```

当前项目：

```text
F01-F05 = STABLE / FROZEN
F06      = NOT STARTED
```

下一阶段计划：

```text
F06 — 人物对白
```

F06 必须基于冻结的 Final Shot ID / Final Timeline 开发，不得重新直接依赖或修改 F04 Auto Candidate。
