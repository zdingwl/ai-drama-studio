# Character Resolution

## 目标

从完整 Episode、CURRENT SOURCE_BIBLE、CURRENT SOURCE_SHOT_FACTS 和 CURRENT SHOT_ANCHORS 中建立稳定 Source Character identity。P7/P8 的 character id 仅作为 candidate；P9 输出新的稳定 identity。

## 执行顺序

1. 读取全部 Episode 和全部 Shot 的人物候选与逐镜绑定，禁止单 Shot 独立归一。
2. 以完整 Episode 直接观察为最高视觉事实，综合人物关系、动作连续性、服装/发型/体态和跨镜上下文。
3. 同名、相似外观都不能单独触发 merge；存在冲突时保持 UNRESOLVED。
4. 服务端验证所有 candidate id、episode id、shot_anchor_id 都属于 CURRENT 上游。
5. 发布 SOURCE_CHARACTERS revision，并记录 fingerprint、ProviderJob、provenance 与 Artifact Graph。

## 禁止

- 不改 P5 Shot 时间。
- 不改 P6 canonical dialogue/OCR。
- 不回写 P7/P8 revision。
- 不把 UNKNOWN/UNRESOLVED 自动填成最高相似候选。
- 不进入 Target 或 P10 Snapshot。
