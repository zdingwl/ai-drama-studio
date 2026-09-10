# Speaker Attribution

## 目标

把 CURRENT P6 canonical utterance 归入稳定 Speaker identity，并在证据足够时把 Speaker 映射到 CURRENT SOURCE_CHARACTERS。Speaker 与 Character 是不同层级，关系允许为空。

## 执行顺序

1. 读取完整 Episode、P6 canonical utterance、P8 provisional speaker candidate 与 P9 Character identity。
2. 直接观看完整 Episode，按 canonical utterance 做全集归因；跨 Shot 的同一 utterance 不重复判定。
3. P8 candidate 只作为 hint；不得因为名称或 P8 候选直接确认最终 Speaker。
4. Speaker→Character 无可靠证据时保持 null + UNKNOWN/UNRESOLVED。
5. 服务端验证 utterance 集合完全等于 CURRENT P6，发布 SOURCE_SPEAKERS revision。

## 禁止

- 不重新 ASR、不改 dialogue text/time。
- 不把相同文本的不同 utterance 自动绑定同一 Speaker。
- 不默认 Speaker 与 Character 一一对应。
- 不进入 P10 Snapshot。
