# Speaker Attribution

## 目标

把 CURRENT P6 canonical utterance 归入稳定 Speaker identity，并在证据足够时把 Speaker 映射到 CURRENT SOURCE_CHARACTERS。Speaker 与 Character 是不同层级，关系允许为空。

## 执行顺序

1. 读取完整 Episode、CURRENT P5 Shot Anchors、P6 canonical utterance、P8 provisional speaker candidate 与 P9 Character identity。
2. 直接观看完整 Episode，按 canonical utterance 做全集归因；跨 Shot 的同一 utterance 不重复判定。
3. P5 Shot start/end 只作为权威时间定位，不允许由 P9 Speaker 归因修改、修正或漂移。
4. P8 candidate 只作为 hint；不得因为名称或 P8 候选直接确认最终 Speaker。
5. Speaker→Character 无可靠证据时保持 null + UNKNOWN/UNRESOLVED。
6. 服务端验证 utterance 集合完全等于 CURRENT P6，发布 SOURCE_SPEAKERS revision。

## 禁止

- 不修改 P5 Shot Boundary 或 Shot 时间。
- 不重新 ASR、不改 P6 canonical dialogue text/time。
- 不把相同文本的不同 utterance 自动绑定同一 Speaker。
- 不默认 Speaker 与 Character 一一对应。
- 不回写 P7/P8 revision。
- 不进入 P10 Snapshot。