# Session Handoff — F01 generate_project_id()

## 本次目标

继续 F01 单函数开发，只完成第三个核心函数：

```text
generate_project_id()
```

本次未新建分支，直接维护用户指定的 `main`；未开始 F02。

## 完成内容

新增：

```text
engine/app/core/ids.py
engine/tests/unit/test_ids.py
```

函数 Contract：

```text
generate_project_id() -> str
```

输出格式：

```text
PROJECT_<32位UUID4小写hex>
```

例如：

```text
PROJECT_86f767c94f2c4f96a1676ce36f615406
```

## 业务规则

Project ID：

- 与项目名称无关；
- 与视频名称无关；
- 与 Workspace Root 无关；
- 与模型/Provider 无关；
- 创建后作为稳定项目身份，后续不得因项目改名或素材变化而改变；
- SQLite `projects.id` 主键是最终冲突保护。

函数自身：

- 不访问数据库；
- 不检查 DB 中是否已存在；
- 不创建 Workspace；
- 不写 `project.json`；
- 不新增第三方依赖。

## 中文注释

`engine/app/core/ids.py` 已写明：

- 业务作用；
- 为什么使用 UUID4；
- 为什么不引入 ULID/雪花算法；
- 输出格式；
- 安全边界。

## 测试

实际执行：

```text
python -m pytest engine/tests/unit/test_ids.py -q
```

结果：

```text
3 passed
```

覆盖：

1. `PROJECT_` 固定前缀；
2. 32 位小写十六进制后缀；
3. UUID 可解析且 version=4；
4. 连续生成 5000 个 ID 无重复。

当前测试运行环境不是最终 Python 3.11 验收环境；F01 完整验收前仍需在目标环境重跑全部测试。

## 文档同步

已更新：

```text
docs/features/F01-create-project.md
docs/features/F01-function-contracts.md
docs/PROJECT_STATE.md
```

## 当前 F01 进度

```text
get_app_data_path()             PASS
init_database()                 PASS
generate_project_id()           PASS
create_project_workspace()      NEXT
create_project()                PLANNED
list_projects()                 PLANNED
open_project()                  PLANNED
recover_creating_projects()     PLANNED
create_app()                    PLANNED
```

## 下一步唯一动作

开发：

```text
create_project_workspace()
```

只负责：

```text
<workspace_root>/<project_id>/project.json
```

下一步重点：

- Workspace Root 默认/传入路径如何解析；
- 只创建当前 Project ID 目录；
- `project.json` V1 字段完全一致；
- 目录冲突时绝不覆盖已有用户文件；
- 写失败时只清理本次新建且可确认归属的半成品目录；
- 不写 `projects` 业务记录；
- 不实现 API；
- 不实现 F02。
