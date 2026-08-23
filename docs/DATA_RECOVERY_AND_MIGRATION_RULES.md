# AI Drama Studio — Data Recovery & Migration Rules

## 1. 目的

本项目同时使用：

- SQLite 保存结构化状态；
- 本地文件系统保存视频、图片、音频、模型缓存和导出物。

数据库事务不能自动覆盖文件系统，因此必须处理：

- 程序崩溃；
- 断电；
- 写盘失败；
- 文件写了一半；
- DB 已记录但文件不存在；
- 文件存在但 DB 未登记；
- migration 中断；
- 项目目录被人工移动/删除部分文件。

---

## 2. 原则：数据库状态不能早于真实文件状态

禁止：

```text
DB: generation.status = completed
↓
开始写 final.mp4
↓
程序崩溃
```

这会留下“数据库说完成，但文件不存在/损坏”的假完成状态。

---

## 3. 媒体写入推荐两阶段流程

适用于 Proxy、Shot cache、Generation、Voice、LipSync、Render 等重要媒体。

```text
1. 创建 DB pending/writing record
2. 计算临时路径 *.tmp / staging
3. 写临时文件
4. flush/close
5. 使用 FFprobe/文件检查校验
6. 必要时计算 size/hash
7. atomic rename/move 到最终路径
8. DB transaction 更新 output_path + ready/completed
9. 记录完成时间
```

最终路径文件未通过校验，不允许 DB 标记 completed。

---

## 4. 临时文件规范

临时文件必须可识别，例如：

```text
v003.mp4.tmp
voice_v002.wav.tmp
render_001.mp4.tmp
```

或统一 staging 目录。

启动时可以扫描：

- 超时的 tmp；
- interrupted operation；
- 是否可恢复；
- 是否应移动到 quarantine。

禁止把残留 `.tmp` 当正式资产使用。

---

## 5. DB Transaction 边界

一个业务操作的 DB 写入必须尽量使用单个明确 transaction。

禁止出现：

```text
写主记录成功
写关系失败
写状态失败
→ 前两步却永久保留为“正常数据”
```

复杂操作应定义：

- prepare；
- commit；
- rollback；
- recovery。

文件系统部分无法与 SQLite 真正形成同一 ACID transaction 时，必须用状态机/操作记录补偿。

---

## 6. 推荐操作状态

对于会写文件的长任务，至少区分：

```text
pending
running/writing
validating
completed
failed
cancelled
interrupted
```

程序启动时发现 `running/writing/validating` 且上次进程已经不存在，应转入：

```text
interrupted
```

然后执行恢复策略，而不是继续假装 running。

---

## 7. Project Integrity Check

项目应逐步具备完整性检查能力，至少能识别：

### Missing file

```text
DB output_path exists
但磁盘文件不存在
```

### Orphan file

```text
磁盘存在 generation/media 文件
但 DB 不存在对应 Asset/Generation 记录
```

### Corrupt file

文件存在但：

- FFprobe 无法读取；
- duration 为 0；
- stream 缺失；
- 文件明显未完整写入。

### Interrupted temp

发现未清理的 staging/tmp。

### Broken relation

例如：

```text
selected_generation_id
指向不存在的 Generation
```

完整性问题不得静默忽略。

---

## 8. Source Asset 保护

Source Video 原则上只读：

- 不覆盖；
- 不在原路径直接重编码；
- 不由缓存清理逻辑删除；
- 不因 Feature 重跑而替换。

如果用户明确替换 Source，应作为显式业务动作，并触发 revision/invalidation 规则。

---

## 9. Migration 前必须备份

每次 Alembic schema migration 前，应用或开发流程必须产生可恢复备份。

建议：

```text
workspace/<project>/backups/
project_YYYYMMDD_HHMMSS_<schema_revision>.db
```

备份至少记录：

- 时间；
- 当前 schema revision；
- 目标 revision；
- 应用版本/commit（能获取时）。

---

## 10. SQLite 备份规则

不要简单在数据库正被写入时用不安全方式复制文件。

应优先使用 SQLite 支持的安全 backup 方式，或确保数据库连接状态满足一致性要求。

如果启用 WAL：

- 必须在环境/数据库初始化文档中明确；
- 备份策略必须考虑 WAL；
- 不允许只复制主 `.db` 却遗漏仍未 checkpoint 的事务。

具体 WAL 策略由首次数据库实现 Feature 测试后冻结。

---

## 11. Migration 规范

每个 migration 文件必须注释：

```text
对应 Feature
为什么需要
新增/修改哪些表字段
是否改变 Frozen Contract
是否可 downgrade
downgrade 风险
数据迁移逻辑
```

禁止直接手工改生产/测试项目 SQLite schema 而不留下 migration。

---

## 12. Migration 失败

流程：

```text
确认备份存在
→ 执行 migration
→ 失败
→ 停止启动需要新 schema 的功能
→ 显示明确错误
→ 提供恢复/重试路径
```

禁止：

```text
migration 失败
→ 忽略
→ 用半新半旧 schema 继续运行
```

---

## 13. 文件命名冲突

所有版本化媒体都应先创建唯一业务 ID/version，再得到目标路径。

禁止使用“如果文件存在就覆盖”。

例如 Generation：

```text
SHOT_023/v003.mp4
```

如果 v003 已经存在，属于数据冲突，需要检查 DB，而不是覆盖。

---

## 14. Hash 与 Size

重要资产建议保存：

```text
file_size
sha256（适用时）
```

用途：

- 检查文件被外部替换；
- 判断重复文件；
- 确认 Provider 下载完成；
- Project integrity；
- 资产来源追踪。

大视频 hash 的性能策略可以后续优化，不要求每个临时缓存都立即 hash。

---

## 15. 删除规则

业务“删除”必须区分：

- 数据库取消引用；
- 移入 trash；
- 真正物理删除。

尤其 Selected / Final / Source / Frozen Contract 相关资产，不允许普通缓存清理误删。

V1 可以简单，但删除行为必须明确，不允许散落 `os.remove()`。

---

## 16. Feature Contract 必须回答

如果 Feature 写 DB 或文件：

1. DB transaction 边界是什么？
2. 文件写入先写哪里？
3. 什么时候认为文件有效？
4. 程序中断后怎么恢复？
5. DB 与文件不一致怎么检测？
6. 是否新增 migration？
7. migration 前怎么备份？
8. 哪些文件可删除，哪些不可删除？

---

## 17. Stable Gate

- [ ] 不存在“DB 先 completed、文件后写”的危险流程
- [ ] 重要文件使用 staging/tmp + validation
- [ ] 崩溃中断状态明确
- [ ] DB transaction 边界明确
- [ ] Migration 有备份与说明
- [ ] Missing/orphan/corrupt 基本处理路径明确
- [ ] Source 不会被意外覆盖/删除
- [ ] 重跑不会覆盖历史版本
