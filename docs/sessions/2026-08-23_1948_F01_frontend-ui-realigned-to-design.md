# F01 前端 UI 重新对齐正式设计规范

时间：2026-08-23 19:48 +08:00  
分支：main（未创建新分支）

## 用户反馈

用户在 Windows 本机真实运行 F01 后指出：当前前端是普通白底页面和普通表单，没有按照此前已经确认的 AI 短剧工厂 UI 规划实现。

该反馈成立。之前为了先跑通 F01 功能，前端只实现了最小功能骨架，错误地把“F01 功能范围最小化”理解成了“视觉层也只做占位原型”。

## 权威视觉基准

重新对齐此前设计文件：

```text
AI短剧工厂界面设计规范.png
```

核心设计规则：

```text
深色专业风格
高对比
内容优先
左侧固定导航
顶部工具栏
统计卡片
最近项目卡片
统一项目工作区 Shell
紫色为主要强调色
```

F01 仍然只实现创建项目能力，不新增 F02 视频上传等业务；但 F01 页面必须使用正式产品设计体系，而不是白底 demo。

## 本次修改

新增：

```text
frontend/src/components/StudioShell.vue
```

重新设计：

```text
frontend/src/views/ProjectHome.vue
frontend/src/components/ProjectCard.vue
frontend/src/components/CreateProjectDialog.vue
frontend/src/views/ProjectWorkspace.vue
frontend/src/styles.css
```

## 首页

调整为正式工作台：

- 深色左侧导航；
- AI短剧工厂 / Drama Studio 品牌区；
- 顶部标题、搜索、新建项目、通知/本地头像；
- 真实项目统计卡，不使用假数据；
- 最近项目封面式卡片；
- 空状态、Loading、错误状态；
- 本地工作区说明和快速新建入口。

统计只从当前 F01 Projects 数据计算：

```text
项目总数
可打开项目
已打开过
本土化目标语言/地区组合
```

不伪造任务进度、积分、模型、视频数据。

## 新建项目弹窗

仍只提交 F01 Contract 允许的字段：

```text
name
source_language
target_language
target_region
workspace_root
```

但视觉改为正式深色卡片式弹层，分为：

```text
01 基础信息
02 本土化设置
03 存储位置
```

新增：

- 完整 submitting loading；
- 关闭重开自动清空旧表单；
- 前端必填校验；
- 本地创建/不上传项目文件提示；
- 错误状态统一展示。

没有提前加入模型、画幅、视频上传等后续 Feature 字段。

## Project Workspace

重新使用统一 StudioShell，并提供：

- 项目总览；
- Project ID / 原语言 / 目标市场 / Format；
- Workspace 状态；
- project.json / DB 状态；
- 7 阶段生产流程视觉轨道。

只有第一阶段“项目创建”为已完成，其余阶段明确显示待开放，不提供可点击功能。

F02 上传原视频按钮仍不存在。

## 开发纪律

以后不能再把：

```text
Feature 范围最小
```

解释为：

```text
页面用无设计的 demo 代替
```

正确规则是：

```text
业务功能严格按 Feature 控制
+
从 F01 起统一使用正式产品 UI Shell / Design System
```

## 当前状态

F01 仍为 IN_PROGRESS，等待用户在 Windows 本机：

```text
git pull origin main
→ npm run dev
→ 刷新浏览器
→ 审核正式深色 UI
```

只有用户确认 UI 与交互后，才能继续 F01 最终验收。
