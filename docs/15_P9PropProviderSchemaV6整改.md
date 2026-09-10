# P9 Prop Provider Schema v6 整改

> 日期：2026-09-10  
> 状态：P9 工程整改；等待同一真实短剧重新运行 Provider 与人工验收。  
> 优先级：本文高于 `docs/14_P9最终归一ProfessionalSkill与数据契约.md` 中 `p9-source-resolution-v5` 的历史运行契约描述；不改变 P9 业务边界，不进入 P10。

## 1. 触发问题

真实 P9 运行已能顺序通过 Character / Speaker / Scene，但在最后的 Prop Provider 阶段持续失败：

```text
P9_PROP_PROVIDER_RESPONSE_INVALID
```

该错误发生于 Provider response 的 Pydantic typed parse 之前/之中，而不是 `_compose_props` 的 P8 observation 集合校验。若进入 composition 后失败，应得到 `P9_PROP_OBSERVATION_SET_INVALID`、`P9_EVIDENCE_REF_INVALID` 等业务错误码，而不是 `P9_PROP_PROVIDER_RESPONSE_INVALID`。

## 2. 确认的工程缺陷

P9 v5 已向 Ark Responses 发送 `strict json_schema`，但生成请求级 Schema 的 `_clean_json_schema()` 继承了早期 prompt-only allowlist，并错误丢弃了 Pydantic 的部分正式约束，包括：

```text
minLength
maxLength
pattern
uniqueItems
以及其他 collection / numeric schema constraints
```

因此存在契约裂缝：

```text
Ark request strict schema
    允许某些过长字符串
        ↓
Provider 返回“符合请求 schema”的 JSON
        ↓
服务端 Pydantic typed schema
    例如 reason max_length=500 / EvidenceRef.note max_length=400
        ↓
拒绝
        ↓
P9_PROP_PROVIDER_RESPONSE_INVALID
```

Prop 阶段需要对实例连续性写理由与 Evidence note，较前三阶段更容易触发这类长度差异，因此该缺陷会优先在 Prop 真实运行中暴露。

这不是放宽 P9 typed schema 的理由。正确修复是让远端请求契约与服务端正式契约一致。

## 3. v6 正式工程契约

当前 P9 Provider 运行契约升级为：

```text
prompt_version = p9-source-resolution-v6
P9 resolution schema = 1.0
source_truth_contract = full-episode-global-resolution-v1
Ark Responses text.format = strict json_schema
Ark Responses max_output_tokens = 65536
```

v6 做以下确定性整改：

1. 请求级 JSON Schema 保留 Pydantic 的 `minLength / maxLength / pattern / uniqueItems / numeric constraints`，不再比服务端 parser 更宽松；
2. Prompt 中展示的 Schema 与 Ark `text.format.schema` 使用同一个 `_provider_json_schema()`，不再存在两套 Schema；
3. Provider 专用 Schema 继续排除 `MANUAL_CONFIRMED`，该状态只允许人工 POST adjudication；
4. Prompt 明确要求 `reason / evidence note` 在 Schema 长度上限内简洁表达；
5. `max_output_tokens=65536` 与 Ark `incomplete` 检测继续保留；
6. typed parse 失败时只暴露安全的字段路径 / 错误类型 /数值约束，不回显原始 Provider 输出；
7. P9 专用 background runner 现在会把安全 AppError message 一并写入 `Task.last_error`，不再只显示错误码。

## 4. 不变的 Source Truth 与安全边界

本次只修 Provider contract alignment，不改变 P9 专业规则：

- 完整 Episode 仍是 Source Truth；
- P5 Shot 时间只读；
- P6 canonical dialogue/OCR 只读；
- P7/P8 仍只是候选和逐镜事实输入；
- Speaker 与 Character 仍严格分层；
- UNKNOWN / UNRESOLVED 仍是一等结果；
- 同名 / 相似外观不触发自动实体合并；
- Prop 仍按持有者、位置、动作、细节与时序连续性判断是否同一实例；
- ProviderJob 仍必须在远程调用前持久化；
- GET 仍只读；
- P5/P6/P7/P8 历史 revision 不回写。

## 5. 重跑规则

`prompt_version` 从 v5 升到 v6，因此 Provider profile / Task fingerprint 已变化。

部署 v6 后必须从 P9 产品入口重新执行一次显式“最终归一”命令，让系统创建基于 v6 fingerprint 的新任务。不要把旧 v5 FAILED Task 作为最终验收对象。

若 v6 仍出现 typed parse 错误，`Task.last_error` 应直接出现安全诊断，例如：

```text
P9 最终归一失败（P9_PROP_PROVIDER_RESPONSE_INVALID）：
prop-resolution Provider 返回结果未通过 P9 数据契约校验
（observations.0.reason:string_too_long[max_length=500]）
```

该提示只含字段路径与契约限制，不包含原始模型正文、API Key 或 Authorization。

## 6. 验收门禁

v6 自动测试必须证明：

- Ark Prop request schema 保留 `group_key maxLength=96`；
- `EvidenceRef.note maxLength=400`；
- `PropObservationSemantic.reason maxLength=500`；
- Provider schema 不含 `MANUAL_CONFIRMED`；
- typed parse 的超长 reason 会给出安全字段级诊断；
- P9 专用 runner 不吞掉上述安全诊断；
- backend compile/import/migrate/pytest 与 frontend typecheck/unit/build 全部通过。

随后仍必须用当前真实短剧完成 P9 的 Provider / 数据 / 音画 /人工 merge-split 验收。只有真实验收全部 PASS 后才能另行评估：

```text
IDENTITY_RESOLUTION
SCENE_RESOLUTION
PROP_RESOLUTION
```

是否从 `PLANNED` 升级。当前仍保持：

```text
IDENTITY_RESOLUTION = PLANNED
SCENE_RESOLUTION = PLANNED
PROP_RESOLUTION = PLANNED
SOURCE_SNAPSHOT = PLANNED
```

P10 `SOURCE_VIDEO_SNAPSHOT` 仍禁止进入。
