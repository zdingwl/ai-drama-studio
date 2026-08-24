# 2026-08-24 — Workflow 01 一步导入原片

## 用户确认的问题

原流程把后端 Feature 拆分直接暴露成用户步骤：

```text
创建项目
→ 视频导入
→ 视频预处理
```

用户明确确认这不合理，导入和初始化应该一步直接完成。

## 正式产品原则

```text
Feature = 内部工程职责 / 数据边界
Workflow = 用户真正操作的步骤
```

用户不再按 F01/F02/F03 页面逐个点击。

## 本轮实现

### 后端

新增：

```text
engine/app/project_import_workflow.py
```

公开编排函数：

```text
import_project_source_workflow()
```

只编排：

```text
create_project()
→ import_source_video()
→ preprocess_source_video()
```

不复制 SQL / FFprobe / FFmpeg / 文件发布逻辑。

新增单一用户 API：

```text
POST /api/project-imports
multipart/form-data
```

字段：

```text
name
source_language
 target_language
target_region
workspace_root
file
```

返回：

```text
status
project
source_video
preprocess
```

Project 创建与 Preprocess 同步工作通过 Starlette threadpool 调用，避免长 FFmpeg 初始化堵住 FastAPI event loop。

### 前端

首页：

```text
新建项目
```

改为：

```text
导入原片
```

弹窗一次填写：

```text
原片文件
项目名称
原片语言
目标语言
目标地区
Workspace Root
```

一次点击：

```text
创建并导入
```

一次 XHR multipart 请求到 `/api/project-imports`。

页面只展示真实可判断的阶段：

```text
发送原片
→ 本地初始化
→ 完成
```

不伪造服务端内部精细进度。

新增：

```text
frontend/src/api/project-import.ts
frontend/src/types/project-import.ts
```

### 导航

项目侧栏切为 Workflow：

```text
01 导入原片
02 拉片
03 人物对白
04 剧本 / 重制设计
05 生成制作
06 最终合成 / 导出
```

旧 source-video / preprocess 等 route 暂时保留，仅用于：

```text
旧项目恢复
中断恢复
开发调试
```

不再是主导航。

## 测试

新增：

```text
engine/tests/unit/test_project_import_workflow.py
```

测试要求 Workflow 只按固定顺序编排 F01/F02/F03 公共能力。

## 当前状态

```text
Workflow 01 = IMPLEMENTED / READY FOR LOCAL TEST
```

还未得到用户真实 Windows 本机验收，因此不能标记 Workflow STABLE / FROZEN。

## 下一步

用户本机验证：

```text
git pull
pytest workflow test
frontend typecheck/build
重启 backend
首页导入一条新视频
确认一次完成 Source + Proxy + WAV + Thumbnail
```

通过后进入：

```text
Workflow 02 — 拉片
```
