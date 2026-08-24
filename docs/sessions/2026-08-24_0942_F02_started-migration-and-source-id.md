# F02 开发启动：Migration Backup Gate + Source ID

时间：2026-08-24 09:42 +08:00  
分支：main（未创建新分支）

## 用户确认

用户确认 F02 主 Contract 和详细函数职责，可以开始编码。

因此：

```text
F02 = IN_PROGRESS
F01 = STABLE / FROZEN
F03 = NOT STARTED
```

## 本轮发现并修正的 Contract 问题

原草案同时要求：

```text
先 DB insert status=importing
```

以及：

```text
sha256 / duration / codec / width / height 等 NOT NULL
```

两者矛盾，因为这些值只有写完文件/FFprobe 后才能知道。

修正为：

```text
importing 阶段允许导入后媒体字段 NULL
ready 阶段由数据库 CHECK 强制核心 metadata 完整合法
```

不允许为了满足 NOT NULL 伪造未知值。

## 已完成 1：0002_create_source_videos

新增：

```text
engine/migrations/versions/0002_create_source_videos.py
```

核心规则：

```text
SOURCE id 主键
project_id FK + UNIQUE
relative_path UNIQUE
status importing / ready
ready metadata CHECK
```

F01 projects 表不做破坏性修改。

## 已完成 2：Migration 前安全 SQLite Backup

修改：

```text
engine/app/core/database.py
```

规则：

```text
fresh DB
→ 直接升级 head
→ 不 backup

existing DB + revision != head
→ sqlite3.Connection.backup()
→ app-data/backups/app_<UTC>_<old-revision>.db
→ backup 成功后 Alembic upgrade

already head
→ 不重复 backup
```

不用 shutil.copy，避免未来 WAL 场景下一致性风险。

## 已完成 3：Source ID

新增：

```text
engine/app/source_videos.py
engine/tests/unit/test_source_video_id.py
```

函数：

```text
generate_source_video_id()
→ SOURCE_<32位UUID4小写hex>
```

只生成 ID，不访问 DB/文件/FFprobe。

## 测试

新增/修改：

```text
engine/tests/unit/test_database.py
engine/tests/unit/test_database_migration_f02.py
engine/tests/unit/test_source_video_id.py
```

隔离工作副本验证：

```text
fresh DB → 0002，无 backup                  PASS
0001 → backup → 0002                       PASS
backup 保留 F01 数据                       PASS
再次 init 不重复 backup                    PASS
importing metadata 可空                    PASS
ready 缺 metadata 被拒绝                   PASS
Source ID 格式 / UUID4 / 5000唯一          PASS
```

Migration 针对性 + Source ID 组合 pytest：

```text
6 passed
```

注意：这不是完整仓库最终 pytest；F02 完成后仍必须完整跑 F01 Regression + F02 tests。

## 当前下一步

只继续第二个核心函数：

```text
copy_upload_to_staging(upload_file, staging_file)
```

职责：

```text
分块读取上传流
→ 写 staging
→ 同时累计 file_size_bytes
→ 同时计算 SHA-256
→ flush/close
```

明确不负责 FFprobe、DB ready、final rename、Proxy/WAV/Thumbnail。
