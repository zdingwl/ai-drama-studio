# F01 桌面端字号可读性修正

时间：2026-08-23 22:10 +08:00  
分支：main（未创建新分支）

## 用户反馈

用户在 1920px Windows 桌面真实运行项目总览后指出：页面整体字体过小。

原因确认：此前为了贴近缩略设计稿，`styles.css` 中大量正文/辅助信息使用了 7–10px，真实桌面端不具备良好可读性。

## 本次处理

新增：

```text
frontend/src/typography.css
```

并在：

```text
frontend/src/main.ts
```

于 `styles.css` 后加载该可读性层。

## 新字号基线

```text
页面标题          20–24px
模块标题          15–17px
导航/按钮/正文    13–14px
辅助信息          11–12px
Project ID         10–11px
```

覆盖范围：

- 左侧全局导航；
- 项目内流程导航；
- 顶部标题和搜索；
- 首页统计卡和项目卡；
- 新建项目弹窗；
- 项目总览 Hero；
- 生产流程；
- Workspace/project.json 状态；
- 下一 Feature 提示。

`CreateProjectDialog.vue` 的下拉框有 scoped 10px 样式，因此 `typography.css` 使用显式覆盖，保证 Select 也按 13px 显示。

## 规则

后续桌面端 UI 不再以设计稿缩略截图中的像素字号直接作为真实运行字号。设计稿可参考层级和密度，但真实 Windows 桌面端正文原则上不低于 12px，主要交互正文使用 13–14px。

F01 业务范围未变化，仍未进入 F02。
