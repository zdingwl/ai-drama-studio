# Session Handoff — 2026-08-28 17:32 +08:00 — P3 Shot Manager UI Rebuild

## 1. 本次目标

用户在浏览器验收 `02 拉片 → 镜头管理` 时明确反馈当前页面难看、信息过多、操作层级不清晰。

本次不是修改 Shot 算法或数据结构，而是把镜头管理从“算法/调试后台”重构成直接的镜头切点审核工作台。

核心产品目标：

```text
选镜头
→ 看原片
→ 判断切点
→ 修正开始/结束
→ 必要时拆分/合并
```

## 2. 开始前仓库事实

读取并遵守：

```text
AGENTS.md
SKILL.md
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
frontend/src/components/BreakdownStageV1.vue
frontend/src/components/ShotWorkbenchV4.vue
frontend/src/components/ShotCacheManagerV51.vue
frontend/src/components/ShotFramePreviewV4.vue
frontend/src/shot-workbench-v3.css
```

当前 P3 状态保持：

```text
implementation = IMPLEMENTED
browser/UI acceptance = IN PROGRESS
fully accepted/closed = NO
```

## 3. 用户反馈对应问题

旧页面主要问题：

- 顶部 `V5.1 拉片缓存` 默认直接展示，RGB / Flow / Qwen / Transition 等内部实现暴露给普通用户。
- 左侧独立剧集列表在单集项目中大量浪费横向空间。
- 中央播放器高度过大，导致一个镜头审核需要长距离上下滚动。
- Shot 列表横向放在页面底部，30+ 镜头查找效率低。
- 右侧同时展示 TransNet、PySceneDetect、帧差、IN/MID/OUT、Cut 对照、输入框和所有操作按钮，信息过密。
- 中英文及工程术语混杂，用户无法快速理解“现在该做什么”。

## 4. 本次实际修改

### 4.1 `ShotWorkbenchV4.vue`

保留现有 Shot / Revision / Reference Clip / 人工边界修改能力，但完整替换默认 UI 布局。

新布局：

```text
顶部：剧集选择 + 镜头数量 + 建议检查数量 + 重新检测 / 批量 / 历史版本

主体三栏：
左：纵向镜头列表
中：当前原片播放器 + 播放位置 + Cut 对照
右：开始 / 结束 / 时长 + 设播放头为边界 + 拆分 + 合并

技术信息：默认折叠
```

删除默认可见内容：

```text
独立剧集侧栏
底部横向 Shots filmstrip
IN / MID / OUT 三联检查帧
TransNet / PySceneDetect / 画面帧差大卡片
Source PTS / Current R 等主界面工程标签
```

保留但降级为高级信息：

```text
边界可信度
TransNet score
画面变化 score
PySceneDetect 辅助状态
Current Revision
Revision kind
```

Cut 边界仍保留，因为它直接帮助用户判断：

```text
当前镜尾帧 | 切点 | 下一镜首帧
```

### 4.2 `BreakdownStageV1.vue`

- 顶部 `镜头管理 / 拉片结果` 切换条压缩高度。
- Tab 文案进一步用户化：
  - 镜头管理：`检查与修正切点`
  - 拉片结果：`查看镜头内容`
- `ShotCacheManagerV51` 不再默认占据镜头工作台顶部。
- 缓存管理移动到底部折叠项：`高级设置与缓存`。

因此 RGB / Flow / Qwen / Transition 等缓存技术信息默认不会出现在用户主要工作流中。

## 5. 保持不变的能力 / Contract

没有修改：

```text
Shot 数据结构
ShotRevision / ShotRevisionItem
Reference Clip
thumbnail / keyframes
TransNet / PySceneDetect 算法
V5.1 cache API
边界定义 [start_us, end_us)
人工开始/结束边界修改 API
split API
merge API
restore revision API
后台任务 API
```

用户界面重排不会改变历史数据或后续 P2 Breakdown / P4 Asset Guidance 的 ShotRevision 锚定逻辑。

## 6. 关键代码提交

```text
5f77fa99bc22a7c4322f2b0e8fe4a434d0b748e2
refactor(ui): rebuild shot manager workspace [skip ci]

e223a2e77418fe73234e6579a1d548ea82921ca5
refactor(ui): compact breakdown navigation [skip ci]
```

## 7. 测试情况

本次环境无法直接访问 GitHub / npm，因此无法在容器内 clone 后运行前端构建。

仓库现有 hosted CI 按项目规则不应为了本次 UI 调整消耗额度；本次提交使用 `[skip ci]`。

此外仓库已知 `vue-tsc + TypeScript 7` CI 兼容问题仍独立存在，本次没有修改依赖版本。

因此本次状态仍然是：

```text
代码已落 main
需要用户本机浏览器验收
P3 UI acceptance 仍为 IN PROGRESS
```

## 8. 浏览器验收重点

请重点检查：

1. `02 拉片 → 镜头管理` 打开后，缓存技术面板不再默认出现。
2. 30 个镜头改为左侧纵向滚动，不再需要底部横向查找。
3. 中央视频在一个工作台高度内完成主要审核，不应再出现旧版超长播放器导致大量纵向滚动。
4. 右侧只突出开始、结束、时长、播放头设边界、拆分、合并。
5. Cut 对照只展示“当前镜尾帧 / 下一镜首帧”。
6. `技术信息` 默认折叠。
7. `高级设置与缓存` 默认折叠。
8. 切换镜头、上一镜/下一镜、修改边界、拆分、合并、历史恢复功能保持可用。

## 9. 风险

- 本次是大幅前端模板重排，需要真实浏览器确认不同分辨率下三栏宽度。
- 竖屏短剧在中央播放器中采用 `object-fit: contain`，预期会出现黑边，但不会再为了铺满宽度而产生超长页面。
- 1040px 以下会降为两栏/顺序布局，需要本地验证窄窗口。

## 10. 下一步唯一推荐动作

> 用户本地拉取 main，刷新 `02 拉片 → 镜头管理`，按第 8 节逐项验收；如果视觉方向认可，再做间距、字号和局部按钮的第二轮微调，不再恢复旧版算法面板式布局。
