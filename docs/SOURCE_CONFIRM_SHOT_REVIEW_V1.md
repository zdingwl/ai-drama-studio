# 原片确认：分镜问题收件箱 V1

## 目标

原片确认只处理 AI 无法自动确定的事实，不按“人物页 / 场景页 / 道具页 / 对白页”拆业务导航。

用户操作单位是 **一个待确认分镜**。

## 用户流程

```text
拉片完成
  ↓
AI 自动完成可确定的人物、场景、道具、对白说话人和 Final Binding
  ↓
只生成真正需要人工判断的分镜任务
  ↓
原片确认
  ↓
左侧：待确认分镜队列
右侧：当前分镜画面 + 当前分镜所有待确认事实
  ↓
在同一个页面直接修改
  - LocalSubject → FinalCharacter
  - 场景
  - 道具
  - 镜头 Final Binding（高级兜底）
  - 对白说话人
  ↓
保存
  ↓
当前分镜仍有问题：留在当前分镜
当前分镜问题清零：自动进入下一条
  ↓
全部清零
  ↓
SourceDramaSnapshot 满足 consumable
  ↓
进入视频重做
```

## 设计约束

1. 不存在“待处理 → 人物/场景/道具 → 人物 → 开始处理”的多层入口。
2. 人物、场景、道具、对白不是页面导航，它们只是当前分镜右侧编辑区中的事实块。
3. 一个跨分镜 LocalSubject 只应产生一次人工身份判断；其他镜头作为证据，不重复要求用户确认。
4. AI 已能确定的结果不进入人工队列。
5. 人物自动解析继续使用 Character V10.1 / Qwen3-VL 结果，人工只处理剩余歧义。
6. Shot Final Binding 的直接编辑属于兜底能力，不应成为普通用户必经步骤。
7. SourceDramaSnapshot 是否可消费仍由后端 FlowState / ReviewIssue / Final Binding 事实决定，前端不能伪造完成状态。

## 当前实现

- `frontend/src/components/SourceConfirmOverlayV3.vue`
  - 单一“原片确认”弹窗，不再提供业务对象 Tab。
- `frontend/src/components/SourceShotReviewWorkspaceV1.vue`
  - 左侧待确认分镜队列。
  - 右侧当前分镜视频 / 图片。
  - 同屏人物身份、场景 / 道具、对白说话人编辑。
  - 保存后重新读取真实后端状态，当前分镜清零后自动进入下一条。
- `frontend/src/App.vue`
  - `mode=confirm` 使用 `SourceConfirmOverlayV3`。

旧 `SourceConfirmOverlayV1/V2` 暂时保留用于回滚，不再作为当前入口。
