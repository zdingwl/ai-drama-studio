# Scene Resolution

## 目标

把 P7/P8 场景候选收敛为稳定全局 Scene identity。Scene identity 由空间事实和连续性决定，不由字符串名称决定。

## 执行顺序

1. 汇总全部 Episode 的 P7 scene candidates、P8 Shot scene bindings 与 P5 shot anchors。
2. 直接观看完整 Episode，判断空间布局、入口/出口、家具与背景结构、时序连续性等。
3. 同一地点跨 Shot 合并；同名但真实空间不同则拆分。
4. 不确定时保留 UNKNOWN/UNRESOLVED。
5. 发布 SOURCE_SCENES，不复制或修改 P5 时间。

## 禁止

- 不按名称直接去重。
- 不修改 P5 Shot Boundary。
- 不回写 P7/P8。
- 不创建 P10 Snapshot。
