# AI Drama Studio — 代码与数据库注释强制规范

> 本规范是项目级强制规则。目标不是增加无意义注释，而是保证用户、后续开发者、ChatGPT、Codex 或其他 Agent 在脱离原对话后，仍能快速理解代码、数据库表、字段和业务逻辑的真实作用。

---

## 1. 总原则

本项目所有新增或修改的业务代码、数据库表、字段、枚举、迁移、复杂算法和外部 Provider 接口，都必须留下足够的中文说明。

注释重点回答：

1. **这个东西是做什么的？**
2. **为什么要存在？**
3. **它在短剧生产流程中的位置是什么？**
4. **输入和输出分别是什么？**
5. **哪些地方不能随意修改？**
6. **如果值为空、失败或改变，会影响什么？**

禁止只把英文变量名机械翻译成中文。

错误示例：

```python
# 项目ID
project_id: str
```

更好的示例：

```python
# 当前记录所属项目的稳定业务 ID。
# 下游 Episode / Scene / Shot 等对象都通过该 ID 归属项目；
# 一旦创建后不得因为项目改名或目录移动而改变。
project_id: str
```

---

# 2. 代码注释规范

## 2.1 文件头说明

核心业务文件应在文件顶部说明：

- 文件负责什么业务能力；
- 属于哪个 Feature；
- 主要输入；
- 主要输出；
- 明确不负责什么；
- 依赖哪些 Stable Contract。

示例：

```python
"""
Feature 04 — 自动拉片

职责：
- 读取 Feature 03 已生成的 proxy video；
- 调用 Shot Detection 模型生成候选镜头边界；
- 保存 AI 原始 detected_start / detected_end。

不负责：
- 不修改人工 final_start / final_end；
- 不执行人物识别；
- 不做 Scene 聚类。

输入：Episode.proxy_video_path
输出：Shot candidate records
"""
```

---

## 2.2 类 / Service / Repository 注释

业务类必须说明它为什么存在以及边界。

```python
class ShotDetectionService:
    """
    自动拉片业务服务。

    只负责从 Proxy Video 生成 Shot Candidate。
    人工修正由 Feature 05 处理，因此本服务禁止覆盖 final_start/final_end。
    """
```

---

## 2.3 函数 / 方法注释

以下函数必须写 docstring：

- 对外 API 调用入口；
- Service 公开方法；
- Repository 数据写入方法；
- Provider Adapter；
- AI 模型推理入口；
- FFmpeg 处理入口；
- 复杂转换/计算函数；
- 有副作用的函数。

至少说明：

```text
用途
参数
返回值
副作用
关键异常
业务约束
```

简单 getter / setter / 明显的一行辅助函数不要求堆积无意义注释。

---

## 2.4 复杂业务逻辑必须写“为什么”

例如：

```python
# 这里保留 detected_start，而不是直接写 final_start。
# 原因：AI 原始结果必须可追溯；Feature 05 的人工修正只能更新 final_start。
shot.detected_start = detected_start
```

比下面这种注释更有价值：

```python
# 设置开始时间
shot.detected_start = detected_start
```

---

## 2.5 AI / 视频算法代码

算法步骤应在关键阶段说明：

```text
输入是什么
为什么采样
为什么使用某个阈值
输出如何解释
Confidence 的范围
失败时怎么处理
```

如果存在经验阈值：

```python
# V1 暂定 0.78 作为同一人物聚类阈值。
# 该值来自开发期样本测试，不属于永久业务 Contract；
# 后续允许通过配置调整，不允许散落硬编码在多个模块。
FACE_CLUSTER_THRESHOLD = 0.78
```

---

## 2.6 Provider / API 代码

必须说明：

- 对应能力，而非只写供应商品牌；
- 请求字段的业务含义；
- 供应商字段如何映射到统一 Contract；
- 返回状态如何映射；
- 哪些供应商特有字段不能泄露到业务层。

示例：

```python
# 将统一 GenerationRequest.duration 映射为当前 Provider 的 seconds 参数。
# 业务层只认识 duration，不允许直接依赖供应商字段名。
```

---

## 2.7 前端 Vue / TypeScript 注释

必须重点注释：

- Pinia Store 中重要状态；
- API DTO；
- Timeline 的时间计算；
- Shot/Scene/Character 之间的关联逻辑；
- 复杂 computed / watch；
- 用户操作为什么会触发某个后端动作；
- 不允许直接修改的 Frozen 数据。

示例：

```ts
/**
 * 当前人工确认后的 Shot 起点（秒）。
 * UI 编辑只修改 finalStart；detectedStart 始终保留 AI 原始值用于对比和回溯。
 */
finalStart: number
```

---

# 3. 禁止的注释方式

禁止：

### 3.1 机械重复代码

```python
# 加 1
count += 1
```

### 3.2 注释与代码不一致

修改逻辑时必须同步修改注释。

### 3.3 大量注释掉的废代码

历史版本交给 Git 管理，不用注释保留整段旧代码。

### 3.4 用 TODO 代替设计

TODO 必须说明：

```text
为什么没完成
影响什么
什么时候处理
对应 Feature / Issue
```

---

# 4. 数据库表注释规范

每一张业务表都必须有中文业务说明。

必须说明：

- 表名；
- 对应业务对象；
- 由哪个 Feature 创建；
- 谁负责写入；
- 哪些 Feature 只读；
- 生命周期；
- 是否属于 Stable / Frozen Contract。

示例：

```text
Table: shots
用途：保存一集短剧中的镜头单元，是后续人物、对白、Scene、生成、QC 的核心关联对象。
创建：Feature 04 自动拉片。
人工修正：Feature 05。
关键约束：detected_* 保存 AI 原始边界，final_* 保存人工最终边界，两者禁止互相覆盖。
```

---

# 5. 数据库字段注释规范

**每个业务字段都必须有字段说明。**

字段字典至少包含：

| 项 | 含义 |
|---|---|
| Field | 数据库字段名 |
| Type | 类型 |
| Nullable | 是否允许为空 |
| Default | 默认值 |
| Business Meaning | 真正业务作用 |
| Source | 谁产生该值 |
| Mutable By | 哪个 Feature 可以修改 |
| Frozen | 是否属于冻结 Contract |
| Example | 示例值 |

示例：

| Field | Type | Business Meaning |
|---|---|---|
| `detected_start` | REAL | AI Shot Detection 首次检测到的镜头开始秒数，只用于保留原始算法结果，不允许人工覆盖 |
| `final_start` | REAL | 人工确认后的最终镜头开始秒数，后续人物、Scene、生成模块应优先读取该值 |
| `selected_generation_id` | TEXT | 当前 Shot 最终选中的生成视频版本 ID；历史 Generation 仍然保留 |

禁止写成：

```text
final_start：最终开始时间
```

这种说明不能让后续开发者理解它与 `detected_start` 的区别。

---

# 6. SQLite 特殊规则

当前项目第一版使用 SQLite。

SQLite 对表/列 COMMENT 的原生支持不像 PostgreSQL/MySQL 那么完整，因此本项目采用 **三层数据库说明**：

### 第一层：SQLAlchemy Model 注释

在 ORM Model 中通过中文 docstring、字段旁注释或 `info` 元数据说明业务含义。

示例：

```python
final_start = mapped_column(
    Float,
    nullable=True,
    info={
        "description": "人工确认后的 Shot 最终开始秒数；下游模块必须优先读取该值。"
    },
)
```

### 第二层：Alembic Migration 注释

每次新增表/字段的 Migration 文件顶部必须说明：

```text
为什么新增
哪个 Feature 使用
字段语义
是否允许回滚
```

### 第三层：Feature 文档字段字典

当前 Feature 的 `docs/features/FXX-*.md` 必须记录完整表和字段字典。

因此即使数据库文件本身无法展示完整 COMMENT，也不能失去字段语义。

---

# 7. 数据库 Model 示例

```python
class Shot(Base):
    """
    短剧镜头业务对象。

    一个 Shot 是系统最小生产单元；人物识别、对白、Scene、AI 视频生成和 QC
    最终都通过 shot_id 关联。
    """

    __tablename__ = "shots"

    # 稳定业务 ID。创建后不因镜头重新检测、文件重命名或生成新版本而变化。
    id: Mapped[str]

    # AI 自动拉片产生的原始起点，人工修正不得覆盖，用于算法回溯与准确率评估。
    detected_start: Mapped[float]

    # 人工确认后的最终起点；只要存在该值，下游 Feature 必须读取它而不是 detected_start。
    final_start: Mapped[float | None]
```

---

# 8. 数据库状态 / 枚举注释

状态值必须说明什么时候进入、谁能改变以及下一合法状态。

错误：

```text
status: pending/running/done
```

正确：

```text
pending：任务已创建但尚未获得执行资源
running：当前 Worker 正在执行，不允许重复提交同一 task_id
completed：任务成功结束且输出已持久化
failed：任务执行失败，可根据 retryable 决定是否重试
cancelled：用户主动取消，不等同于 failed
```

---

# 9. API Schema 注释

Pydantic / TypeScript DTO 中重要字段都必须写业务说明。

FastAPI 应尽量利用：

- `Field(description="...")`
- Schema docstring
- endpoint `summary` / `description`

让 `/docs` 能直接成为可阅读接口文档。

示例：

```python
final_start: float | None = Field(
    default=None,
    description="人工确认后的 Shot 最终开始秒数；为空表示尚未进行人工确认。",
)
```

---

# 10. 每个 Feature 必须维护 Database Dictionary

如果当前 Feature 新增或修改数据库结构，其 Feature 文档必须增加：

```text
## Database Dictionary
```

并逐表逐字段说明。

不得只贴 SQL。

例如：

```text
projects
├ id                  稳定项目ID
├ name                用户看到的项目名称，可修改
├ workspace_path      项目素材根目录
└ created_at          项目首次创建时间
```

每个字段继续补充：来源、可修改者、Null 行为、默认值和下游用途。

---

# 11. 每次开发结束的注释验收

Session Handoff 前必须检查：

- [ ] 新增核心文件有文件职责说明
- [ ] 新增核心类有业务边界说明
- [ ] 新增公开方法/复杂函数有 docstring
- [ ] 复杂算法写清“为什么”
- [ ] 新增 API Schema 的重要字段有 description
- [ ] 新增数据库表有业务说明
- [ ] 新增/修改数据库业务字段都有字段说明
- [ ] Alembic Migration 有迁移目的说明
- [ ] Feature 文档中的 Database Dictionary 已同步
- [ ] 注释与当前实现一致，没有过期注释

任何一项缺失：

> 本次代码交付不能视为文档完整。

---

# 12. Feature Stable Gate 增加注释检查

Feature 标记 `STABLE / FROZEN` 前必须增加：

```text
CODE COMMENT REVIEW: PASS
DATABASE COMMENT REVIEW: PASS
DATABASE DICTIONARY: COMPLETE
```

否则不能 Freeze。

---

# 13. 语言规范

因为项目主要由中文用户理解和维护：

- 业务解释优先使用**简体中文**；
- 类名、变量名、表名、字段名保持规范英文；
- 专业英文术语可保留，如 Shot、Scene、Character Bible、Provider；
- 注释第一次出现专业术语时尽量解释其业务含义；
- 不要求把成熟技术名强行翻译成不自然中文。

推荐：

```python
# Shot 的最终人工确认起点。Shot 指原剧经过自动拉片后形成的最小镜头单元。
final_start: float
```

---

# 14. 核心目标

本规范不是为了“注释越多越好”。

真正目标是：

> **任何新的开发人员或新对话中的 AI，只阅读当前代码、数据库字典和 Feature 文档，就能够理解数据为什么这样设计、应该由谁修改、下游应该读取哪个字段，以及哪些 Contract 不能破坏。**
