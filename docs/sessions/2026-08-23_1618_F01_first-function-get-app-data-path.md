# Session Handoff — F01 第一个函数 get_app_data_path

## 本次目标

用户确认简化版 F01 Contract 后正式开始开发，但严格执行“单函数 → 测试 → PASS → 下一个函数”。

本次只完成第一个核心函数：

```text
get_app_data_path()
```

没有创建新分支，直接维护用户指定的 `main`。

## 完成内容

新增：

```text
engine/app/core/paths.py
engine/tests/unit/test_paths.py
pyproject.toml
```

`get_app_data_path()` 的业务作用：

- 返回 AI Drama Studio 应用级数据目录；
- 开发/测试优先读取 `AI_DRAMA_APP_DATA_DIR`；
- Windows 正式默认 `%LOCALAPPDATA%/AI Drama Studio`；
- 只解析路径，不创建目录；
- 无法确定目录时明确失败，不静默写到当前工作目录。

代码包含简体中文文件说明和函数 docstring，解释业务作用、为什么无副作用、安全边界和异常。

## 测试

本地执行：

```text
pytest engine/tests/unit/test_paths.py
```

结果：

```text
4 passed
```

覆盖：

1. `AI_DRAMA_APP_DATA_DIR` 覆盖优先；
2. 没有覆盖值时使用 `LOCALAPPDATA/AI Drama Studio`；
3. 空白覆盖值不会错误解析成当前目录；
4. 两种位置都无法确定时明确抛错；
5. 函数不会偷偷创建目录。

第一次测试收集阶段因仓库尚无 pytest root 配置导致 `ModuleNotFoundError: engine`，随后增加根 `pyproject.toml` 的 pytest `pythonpath = ["."]`，无修改业务函数逻辑，重新运行后 4/4 PASS。

## 环境说明

本次执行容器：

```text
Python 3.13.5
pytest 9.0.2
```

仅用于验证当前纯路径函数逻辑。项目正式环境仍按 Python 3.11，F01 完整验收前必须在目标环境执行完整测试，因此不能据此把 Environment Gate 标记 PASS。

## 当前状态

```text
F01: IN_PROGRESS
get_app_data_path(): TESTED / PASS
init_database(): NEXT
Business DB/Migration: NOT_STARTED
Frontend: NOT_STARTED
F02: NOT_STARTED
```

## 下一步

只开发：

```text
init_database()
```

范围：应用级 `app.db` + `projects` 表初始化。

明确不做：Project Workspace、project.json、项目创建 API、视频上传或任何 F02 内容。
