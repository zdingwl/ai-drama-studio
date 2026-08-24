# F03 — 已部署 0003 Audio CHECK 兼容修复

日期：2026-08-24 11:57 +08:00  
分支：main  
Feature：F03 — 视频预处理  
状态：READY_FOR_REVIEW / 用户复测中

## 用户真实现象

F03 页面 GET `/preprocess` 返回 200 null，但点击“开始视频预处理”后 POST 返回：

```text
409 Conflict
视频预处理记录已经存在，请稍后再试
```

用户 Source 有 AAC 音频。

## 根因

不是新的 stale-processing Recovery 再次失效，而是用户 `app.db` 已经执行过早期版本：

```text
0003_create_source_preprocess
```

早期 0003 使用：

```text
ck_source_preprocess_audio_all_or_none
```

它要求 Audio 字段“全空或全完整”。但 F03 正常 processing 阶段需要先写：

```text
audio_relative_path = preprocess/SOURCE_xxx/audio.wav
```

而 size/hash/duration 等只有 FFmpeg 完成后才知道，因此旧 CHECK 会拒绝合法 INSERT。

后续虽然修改了仓库中的 0003 Migration 文件，但 Alembic 不会重新执行已经落在用户数据库上的同 revision，因此用户数据库仍保留旧约束。

此外 SQLAlchemy `IntegrityError` 当时统一映射为 `PREPROCESS_IN_PROGRESS`，导致页面文案看起来像“记录仍存在”。

## 正式修复

新增：

```text
engine/migrations/versions/0004_repair_source_preprocess_audio_constraint.py
```

升级：

```text
0003 → SQLite Backup Gate → 0004
```

0004：

- 检测旧 `ck_source_preprocess_audio_all_or_none`；
- 使用 Alembic SQLite batch rebuild；
- 替换成 `ck_source_preprocess_audio_ready_consistency`；
- processing 允许先保存 audio target path；
- ready 才强制 Audio metadata 完整；
- 保留 F01/F02/F03 已有 DB 数据；
- 不修改 Project Workspace、F02 original 或派生媒体。

全新数据库当前 0003 已经正确，因此 0004 检测新约束存在后不重复重建。

## 测试补充

新增：

```text
engine/tests/unit/test_database_migration_f03_compat.py
```

覆盖：

- 历史旧 0003 确实拒绝 processing + audio target path；
- `init_database()` 自动产生旧 0003 backup；
- 升级后 revision 为 0004；
- 旧约束消失，新约束存在；
- processing + audio target path 可以正常落库；
- 当前正确 0003 → 0004 不重复破坏表结构。

同时更新 `test_database_migration_f03.py` 的当前 head 断言为 0004。

## 独立机制验证

在隔离 SQLite + SQLAlchemy 2.0.50 + Alembic 1.18.4 环境实际验证：

```text
old check detected
→ batch drop old check
→ create new check
→ table rebuild success
→ processing + audio target path INSERT success
```

## 用户复测

```powershell
cd E:\ai-drama-studio
git pull origin main
```

停止并重新启动 FastAPI，让 startup 执行 0004：

```powershell
python -m uvicorn engine.app.main:app --host 127.0.0.1 --port 8080 --reload
```

浏览器 `Ctrl + F5` 后重新点击“开始视频预处理”。

禁止要求用户手工删除 app.db、projects、source_videos 或 F02 原片。
