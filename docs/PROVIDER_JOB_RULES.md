# AI Drama Studio — Provider Job Rules

## 1. 目的

外部 VLM、视频生成、TTS、Lip Sync 等 Provider 可能：异步执行、计费、限流、超时、返回 task id、程序重启后仍继续运行。

核心目标：

> 网络超时或本地重启不能导致重复付费任务、任务丢失或历史版本被覆盖。

---

## 2. 本地 Job 先于远端请求创建

调用 Provider 前必须先持久化本地记录，至少包含：

```text
local_job_id
request_id
request_fingerprint
attempt
provider
model
status
created_at
```

推荐状态：

```text
created
submitting
submitted
running
completed
failed
cancelled
unknown
```

`unknown` 表示本地无法确认远端是否创建成功，不能直接当 failed 自动重提。

---

## 3. Idempotency

如果 Provider 支持 idempotency key，必须使用稳定 key。

如果不支持，也必须保存：

```text
request_fingerprint
```

Fingerprint 应基于会决定远端任务内容的稳定输入生成，例如：

```text
provider + model + normalized request + input asset ids/hashes + shot spec revision
```

其用途是识别“这是不是同一次业务请求”，不是强制复用结果。

---

## 4. provider_task_id 立即持久化

一旦远端返回：

```text
provider_task_id
```

必须立即写入 DB。

后续查询只围绕该 task id 进行。

应用重启后：

```text
status=submitted/running
+ provider_task_id exists
→ resume query/poll
```

禁止重新创建远端任务。

---

## 5. Timeout 语义

HTTP timeout 只表示：

> 本地没有及时收到响应。

它不证明 Provider 没收到请求。

因此：

```text
submit timeout
→ status = unknown
→ 尝试通过 provider idempotency/status/query 能力确认
→ 确认未创建后才允许安全重试 submit
```

禁止默认：

```text
timeout → failed → 自动重新付费生成
```

---

## 6. Retry 分类

错误至少分：

### Safe retry

例如明确的连接建立失败，且可确认请求未送达；或 Provider 文档明确支持同 idempotency key 重试。

### Poll retry

远端任务已创建，只重试状态查询/下载，不重新创建任务。

### Manual review

无法确认远端是否已创建、Provider 状态异常、计费状态未知。

### Non-retryable

输入非法、内容策略拒绝、余额不足、模型不支持参数等。

每个 Provider Adapter 必须定义错误映射。

---

## 7. Attempt 与 Version

人工点击“重新生成”时：

- 创建新的 attempt / generation version；
- 保留旧 job；
- 记录 `retry_of` / `parent_job_id`（如采用）；
- 不覆盖旧 output；
- 新成本独立记录。

自动网络重试如果仍属于同一远端 task，则不应创建新的 Generation Version。

---

## 8. 下载结果

Provider 返回下载 URL 后：

```text
下载到 staging/tmp
→ 校验 HTTP/size/media
→ 必要时 hash
→ atomic move
→ DB completed
```

下载失败只重试下载，不重新提交生成任务。

---

## 9. Cancel

如果 Provider 支持 cancel：

- Adapter 负责映射；
- 本地记录 cancel request；
- 只有确认远端取消后才能标记 cancelled；
- 如果 Provider 不支持取消，UI 要明确“停止本地等待不等于停止远端计费”。

---

## 10. Cost

能获得时必须记录：

```text
estimated_cost
actual_cost
billing_unit
provider_usage
```

如果只能估算，字段必须标明 estimated，不能冒充实际账单。

---

## 11. Secrets 与日志

日志禁止输出：

- API Key；
- Authorization header；
- 完整签名 URL（如含敏感 token）；
- Provider secret。

允许记录可诊断但不敏感的 request id、task id、model、status、error code。

---

## 12. Provider Adapter Contract

业务层只处理统一对象，例如：

```text
GenerationRequest
ProviderJob
GenerationResult
```

供应商特有状态必须在 Adapter 中映射。

禁止业务层到处直接判断：

```text
if provider == "xxx" and raw_status == "..."
```

---

## 13. 应用启动恢复

启动时扫描未终态 job：

```text
submitted/running + provider_task_id
→ resume poll

unknown
→ attempt reconciliation

created/submitting 且无 task id
→ 根据日志/idempotency 判断，不盲目重提
```

恢复行为必须写入日志和 Session 测试记录。

---

## 14. Feature Contract 必须回答

调用外部 Provider 的 Feature 必须写清：

1. local_job_id 何时创建？
2. request_fingerprint 如何产生？
3. Provider 是否支持 idempotency？
4. provider_task_id 何时保存？
5. timeout 怎么处理？
6. 哪些错误可安全 retry？
7. 重启后如何恢复？
8. 下载失败是否会误触发重新生成？
9. 成本如何记录？
10. 人工重新生成如何版本化？

---

## 15. Stable Gate

- [ ] submit timeout 不会直接重复付费任务
- [ ] provider_task_id 持久化
- [ ] restart resume 已定义
- [ ] poll retry 与 submit retry 已区分
- [ ] 手工 regenerate 会新建版本
- [ ] 下载失败不会重提生成任务
- [ ] Provider raw status 已在 Adapter 隔离
- [ ] Secret 不进入日志
