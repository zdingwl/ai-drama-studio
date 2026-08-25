# 02 拉片 V4：Frame-Accurate Boundary

## 目标

解决旧拉片中“上一 Shot 尾部带出下一 Shot 第一帧”的系统性边界问题，并提供肉眼可快速验收的边界 QC。

## 正式流程

```text
25fps Analysis Proxy
  -> TransNetV2 transition candidates

Source Video
  -> PySceneDetect AdaptiveDetector (secondary evidence only)
  -> Source frame PTS
  -> low-res sequential frame delta

TransNet candidate
  -> map to Source timeline
  -> search +/- 5 Source frames
  -> choose strongest adjacent-frame boundary
  -> PySceneDetect confirmation / confidence
  -> Final Cut Source PTS

Final Cuts
  -> Shot [start_us, end_us)
  -> exact Reference Clip
  -> IN / MID / OUT review times
  -> OUT | NEXT IN visual QC
```

## 硬规则

1. **TransNetV2 负责发现候选区域，不直接决定最终微秒 Cut。**
2. **PySceneDetect 是第二证据，不允许与 TransNet 简单 union。** PySceneDetect-only cut 暂不自动新增 Shot，防止过切。
3. **最终 Cut 必须落到 Source frame PTS。** Proxy 仅用于模型候选检测。
4. **Shot 时间区间永远是 `[start_us, end_us)`。**
   - `start_us`：当前 Shot 第一帧。
   - `end_us`：下一 Shot 第一帧，不属于当前 Shot。
   - `OUT`：严格取 `end_us` 之前最后一个 Source frame。
5. **Reference Clip 视频 trim 的 end 必须是排他的。** 原视频/音频先 PTS 归零，再 trim。
6. **原片首帧 PTS 非零时统一以首帧为 0。** Proxy 和 Source 共享同一业务时间原点。
7. **低置信边界只进入“待检查”，不会阻塞整集拉片。**
8. **人工修改仍创建 MANUAL Revision，历史 Revision 不覆盖。**

## 边界置信度

当前组合：
- TransNet peak score：38%
- Source adjacent-frame visual evidence：47%
- PySceneDetect confirmation：15%

以下情况进入待检查：
- confidence < 0.68；
- Source 相邻帧变化弱；
- PySceneDetect 已运行但未确认；
- Source PTS 精修相对 TransNet 候选偏移 >= 4 帧；
- Shot < 500ms。

## UI 验收

选中任意 Shot 后必须同时看到：
- IN 首帧；
- MID 中间帧；
- OUT 尾帧；
- 当前 OUT 与下一 Shot IN 并排 Cut 对照；
- TransNet / Source frame delta / PySceneDetect / 综合置信度；
- 待检查原因。

检查帧支持点击放大、滚轮缩放和 1:1。

## Release Gate

先用真实第 01 集验收：

- 连续检查所有 `OUT | NEXT IN`；
- 上一 Shot OUT 不得出现下一 Shot 的第一帧；
- 下一 Shot IN 必须是新镜头第一帧；
- 低置信度/渐变转场进入待检查；
- 确认无系统性 +1 frame 偏移后，再批量重跑全剧，并让 03 资产重新分析。
