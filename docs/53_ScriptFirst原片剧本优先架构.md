# Script-first 原片剧本优先架构

> 日期：2026-09-13
> 状态：正式架构整改合同。本文替代 `docs/21~23` 中“必须等 P5~P10 全链完成后才能拿到原片剧本并进入 Target”的旧顺序；P5~P10 已验收能力本身不删除。
> 目标：上传原片后尽快得到正式 `SOURCE_SCRIPT`，后续语义改编以剧本为主输入；镜头、视觉 identity、精确 shot timing 继续由后台增强链提供给真正需要视觉精度的生产阶段。

## 1. 产品主线

```text
上传完整原片
→ Canonical Dialogue / OCR
→ Whole-Episode Understanding
→ SOURCE_SCRIPT（立即可用）
→ Target Bible / Target Script / Target Assets / Target Audio

后台继续：
Shot Anchors → Shot Breakdown → Identity / Scene / Prop Resolution → SOURCE_VIDEO_SNAPSHOT
→ 在 Target Storyboard / Video Generation 前完成视觉对齐
```

用户不应为了拿到剧本等待逐镜拉片、人物最终归一和 Snapshot publication。

## 2. SOURCE_SCRIPT 定义

`SOURCE_SCRIPT` 是正式 Source Artifact，不是 UI 临时视图。它由 CURRENT：

```text
SOURCE_VIDEO
+ SOURCE_DIALOGUE
+ SOURCE_BIBLE
```

确定性投影发布，不额外调用模型。

内容至少包含：Episode、canonical dialogue + 时间、timed story segments、人物候选、场景候选、关键道具、Story Skeleton、Rhythm Skeleton。

完整 Episode 仍是最终 Source Truth；`SOURCE_SCRIPT` 是后续语义创作的 canonical working truth。

## 3. 双链职责

### Script semantic chain

负责：故事、人物功能、人物关系、对白、本土化、节奏、剧情事件。P11/P12 优先消费 `SOURCE_SCRIPT`。

### Visual grounding chain

负责：精确 Shot、镜头语言、人物视觉 identity、场景空间、道具实例、说话人最终归一。P8/P9/P10 可以在 SOURCE_SCRIPT 发布后继续运行。

P15 及后续真正生成画面的阶段仍必须等待完整 `SOURCE_VIDEO_SNAPSHOT`。

## 4. Identity reconciliation

P7 candidate identity 是 Script semantic identity；P9 stable identity 是 Visual resolved identity。

P9 已保存 `source_candidate_ids`。后续 Production 必须通过这些 candidate binding 把 P7 script identity 对齐到 P9 stable identity：

- direct stable id match 优先；
- 否则用 `source_candidate_ids` 唯一匹配；
- 多候选映射到多个 Target identity 时 fail closed；
- 禁止按名字字符串静默猜测。

## 5. Source Analysis 行为

一次显式“解析原片”仍可继续完整跑 Source 链，但状态和结果允许分阶段可用：

```text
P6 + P7 完成
→ 发布 CURRENT SOURCE_SCRIPT
→ 页面立即显示剧本，可进入语义改编

P8 + P9 + P10 继续
→ 完成视觉增强与 Production-ready Source Snapshot
```

GET 继续只读；SOURCE_SCRIPT publication 发生在用户显式启动的 Source Analysis Task 内。

## 6. 兼容与状态

P0~P13 的历史真实验收事实不被本文撤销。本文是架构顺序调整，不把 P14~P17 提前标记 PASS。

P14~P17 当前仍保持 `PASS = NO`，对应未真实验收 capability 仍为 `PLANNED`。
