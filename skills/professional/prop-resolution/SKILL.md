# Prop Resolution

## 目标

把剧情相关的 P7/P8 道具候选整理为稳定的 Source Prop identity，并区分“同类物件”和“同一个具体实例”。

## 执行规则

1. 汇总全部 Episode 的 key prop candidates、P8 Shot bindings 与 P5 anchors。
2. 直接观看完整 Episode，综合持有者、位置、连续动作、可见细节和时序判断实例连续性。
3. 同一具体实例可以跨 Shot merge；证据不足时保持 UNRESOLVED。
4. 只保留剧情相关道具，不把普通背景物件扩展为正式实体。
5. 发布 SOURCE_PROPS revision，保留 fingerprint、provenance 和 Artifact Graph。

## 边界

不得修改 P5/P6/P7/P8 历史事实，不进入 Target，不创建 P10 Snapshot。
