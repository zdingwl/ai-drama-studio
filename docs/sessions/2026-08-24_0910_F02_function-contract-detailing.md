# F02 函数职责详细化记录

时间：2026-08-24 09:10 +08:00  
分支：main（未创建新分支）

## 用户反馈

用户指出 F02 主 Contract 中：

```text
generate_source_video_id()
copy_upload_to_staging()
probe_source_video()
import_source_video()
get_source_video()
recover_source_video_imports()
```

以及：

```text
GET  /api/projects/{project_id}/source-video
POST /api/projects/{project_id}/source-video
```

只是列出了函数/路由，没有真正解释“具体是干什么的”。

该反馈成立。

## 本次调整

新增：

```text
docs/features/F02-function-contracts.md
```

为 F02 的 6 个核心后端函数 + 2 个 Controller 分别写清：

```text
真实业务作用
为什么要存在
谁调用
输入
输出
文件副作用
数据库副作用
外部程序调用
失败边界
明确禁止行为
测试范围
```

## 重要原则

F02 仍保持小规模核心函数，不继续拆成几十个 helper。

详细 ≠ 函数多。

正确目标：

```text
核心函数数量少
+
每个核心函数职责讲透
+
简单 helper 只写必要中文注释和测试
```

## 当前状态

```text
F01 = STABLE / FROZEN
F02 = PLANNED
F02 Main Contract = DRAFTED
F02 Function Contracts = DETAILED
F02 Business Code = NOT STARTED
F03 = NOT STARTED
```

仍等待用户审核/确认 F02 Contract 后再进入编码。
