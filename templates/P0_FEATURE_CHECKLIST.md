# P0 Feature Checklist

> 每个 Feature 在开始编码前必须复制本清单到对应 `docs/features/FXX-*.md`。
>
> 所有项目必须填写 `PASS / N/A`，禁止留空。`N/A` 必须说明原因。

## P0-01 Dependency / Revision / Invalidation

- 适用：Yes / No
- 原因：
- 本 Feature 依赖哪些上游 revision：
- 本 Feature 产生哪些派生结果：
- 哪些上游变化会使结果 stale：
- stale 后 UI/后端如何处理：
- 如何重新计算：
- 是否允许人工 override：

开发完成：`PASS / N/A`

---

## P0-02 Media Timebase

- 适用：Yes / No
- 原因：
- 输入 timeline：
- 输出 timeline：
- 权威单位：integer microseconds
- 是否涉及 Source↔Proxy 映射：
- 是否涉及 VFR：
- 是否涉及音频 sample rate：
- rounding 使用的公共方法：
- 时间误差测试：

开发完成：`PASS / N/A`

---

## P0-03 Environment Baseline

- 适用：Yes / No
- 是否新增 Python/Node/native 依赖：
- 是否新增本地模型：
- 精确版本/lock 更新：
- 模型来源/hash：
- 是否影响 RTX 4060 Ti 16GB：
- 新电脑安装/验证步骤：

开发完成：`PASS / N/A`

---

## P0-04 DB + File Recovery

- 适用：Yes / No
- DB transaction 边界：
- 是否写媒体/缓存文件：
- staging/tmp 策略：
- 文件校验：
- 崩溃中断状态：
- restart recovery：
- 是否新增 migration：
- migration backup：
- orphan/missing file 处理：

开发完成：`PASS / N/A`

---

## P0-05 Provider Job Safety

- 适用：Yes / No
- Provider：
- local_job_id 创建时机：
- request_fingerprint：
- idempotency 支持：
- provider_task_id 持久化：
- submit timeout 处理：
- poll retry：
- restart resume：
- 人工 regenerate versioning：
- cost 记录：

开发完成：`PASS / N/A`

---

## Stable Gate

```text
P0 DEPENDENCY REVIEW: PASS / N/A
P0 TIMEBASE REVIEW: PASS / N/A
P0 ENVIRONMENT REVIEW: PASS / N/A
P0 RECOVERY REVIEW: PASS / N/A
P0 PROVIDER JOB REVIEW: PASS / N/A
```

任一适用项未 PASS：Feature 不得进入 STABLE / FROZEN。