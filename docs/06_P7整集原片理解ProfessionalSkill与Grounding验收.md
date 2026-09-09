# P7 整集原片理解 Professional Skill 与 Grounding 验收

> 更新时间：2026-09-09  
> 当前状态：**P7 已通过真实短剧人工验收**。  
> 最终验收记录与 Provider readiness 见：`docs/07_P7最终验收与ProviderReadiness.md`。

---

# 1. Professional Skill

正式 Professional Skill：

```text
skills/professional/episode-understanding/SKILL.md
skills/professional/episode-understanding/manifest.json
source-video-understanding@1.1.0
```

正式关系：

```text
Root Project Skill
→ source-video-understanding Professional Skill
→ Provider Prompt
→ Grounded Schema
→ Provider Guardrail
→ Service Publication Guardrail
→ SOURCE_BIBLE
```

Professional Skill 不是 Prompt；Doubao / Qwen Provider 必须执行同一套业务判断规则。

---

# 2. Source Truth 层级

```text
完整 Episode / SOURCE_VIDEO
= 最高层原片事实源

CURRENT P6 Source Evidence
= canonical dialogue / OCR 文字事实源

CURRENT Shot Anchors
= 可选时间定位提示
= 不是剧情事实源
= 不是剧情分段边界
```

禁止把 Reference Clip 逐个分析后拼成整集理解。

---

# 3. Grounding v2

正式契约：

```text
grounded-source-truth-v2
SOURCE_BIBLE schema 1.1
p7-source-bible-v2
```

事实等级：

```text
FACT
= 原片直接可见或 CURRENT Evidence 明确陈述

INFERENCE
= 有依据的合理推导，但原片未直接确认

UNKNOWN
= 无法可靠判断
```

发布规则：

```text
FACT / INFERENCE
→ 至少有 CURRENT Evidence ID 或完整 Episode video_time_ranges

UNKNOWN
→ 不携带 Evidence / video range
→ 只能对应省略 / null 的未确认 claim
→ 不能与确定性事实正文一起发布
```

核心原则：**UNKNOWN 不是绕过 Source Truth 校验的通行证。**

---

# 4. 必须 FACT-grounded 的 Source Facts

当前正式字段中，以下如果存在必须 FACT-grounded：

```text
overall_analysis.story_background
characters[].identity
relationships[]
scenes[]
story_events[]
key_props[].appearance_state
world_rules[]
```

`world_rules` 只允许本作品内部已确认规则；没有内部规则时：

```json
{
  "world_rules": [],
  "world_rule_groundings": []
}
```

禁止社会经验泛化、法律结论、道德训诫和片外常识扩写。

---

# 5. 道具 Grounding

道具拆分：

```text
appearance_state
= 可见事实
= 必须 FACT

story_function
= 剧情作用
```

`story_function`：

```text
原片直接确认 → FACT
有依据但未直接确认 → INFERENCE
无法确认 → null + UNKNOWN
```

真实短剧中“黑色垃圾袋”最终验收结果已符合：只保留手持垃圾袋的可见事实，不再补写“倒垃圾时顺手拿花”等因果。

---

# 6. 双层 fail-closed

正式运行：

```text
Provider response
↓
Provider grounding validation
↓
Pydantic parse
↓
Service publication grounding validation
↓
Episode / Evidence / character reference validation
↓
全部通过才发布 SOURCE_BIBLE
```

以下必须失败且不能发布半成品：

- Evidence ID 不存在或不属于 CURRENT Episode；
- FACT / INFERENCE 没有支持；
- UNKNOWN 携带 support；
- 确定性 Source Fact 标 UNKNOWN；
- world_rules / groundings 数量不一致；
- world rule 非 FACT；
- prop appearance 非 FACT；
- prop story_function 为 UNKNOWN 但正文非空；
- grounding 时间越过 Episode；
- relationship 引用不存在角色；
- Provider 输出 Schema 非法；
- Task 执行期间上游 Source / Evidence / Provider profile 改变。

P6 Source Evidence 在任何失败中都不能被改写。

---

# 7. Evidence 引用稳定性

真实运行暴露出模型精确复制长 UUID 的脆弱性，因此正式实现使用：

```text
P6 canonical Evidence UUID
↓
Provider 输入前生成 D0001 / O0001 等短引用
↓
模型只引用短 ID
↓
服务端确定性恢复 canonical UUID
↓
Grounding / CURRENT Evidence 校验
```

未知短引用仍 fail closed，不做猜测修复。

---

# 8. Provenance

SOURCE_BIBLE provenance 直接记录：

```text
prompt_version = p7-source-bible-v2
schema_version = 1.1
professional_skill_id = source-video-understanding
professional_skill_version = 1.1.0
grounding_contract = grounded-source-truth-v2
```

同时保留：

- SOURCE_VIDEO Artifact ID / fingerprint；
- SOURCE_DIALOGUE Artifact ID / fingerprint；
- 可选 Shot Anchors ID / fingerprint；
- Episode Evidence Set ID / fingerprint；
- ProviderJob ID；
- provider / model；
- remote response ID；
- generated Task ID。

这些关键版本进入 task / provider profile fingerprint。

---

# 9. v1 → v2 STALE

Alembic `0010_p7_grounding_contract_v2` 已用于使 v1 旧理解链失效：

```text
旧 SOURCE_BIBLE       → STALE
旧 STORY_SKELETON     → STALE
旧 RHYTHM_SKELETON    → STALE
P6 Source Evidence    → CURRENT
```

---

# 10. 最终真实短剧验收

真实 Episode：

```text
货到付款惩治隔壁大妈-第01集.mp4
约 66 秒
```

真实 Provider：

```text
Volcengine Ark
Doubao Seed 2.1 Pro
```

最终验收确认：

- `128 元` 与 canonical dialogue 一致；
- `结婚八年` 与 canonical dialogue 一致；
- 人物姓名 / 身份能由 OCR / 视频依据支撑；
- world_rules 正确为空 / 无明确片内规则；
- 不再出现社会泛化和法律结论；
- 黑色垃圾袋未确认剧情作用时为 null / UNKNOWN；
- scene / event / relationship 等正式事实不再通过 UNKNOWN 逃逸；
- 故事概述、人物关系、时间化剧情、Story Skeleton、Rhythm Skeleton 质量未因 Grounding 收紧而退化；
- 时间化剧情保持剧情语义窗口，不冒充 Shot Boundary；
- Evidence 默认折叠但可反查 P6 canonical 正文；
- 类型与世界规则分离展示；
- Revision / Provenance 可展开审计；
- API Key UI 默认密码遮罩，显式点击后才查看原文。

因此本轮判定：

```text
P7 = ✅ 已完成真实人工验收
EPISODE_UNDERSTANDING = AVAILABLE
STORY_RHYTHM = AVAILABLE
```

---

# 11. Provider readiness

业务 Capability 验收与每个 Provider 的 readiness 分开：

```text
Doubao Seed 2.1 Pro    ✅ 当前环境真实验收通过
Qwen3.8-27B            ⏳ 工程接入完成，待本机 vLLM 实测
Qwen3-VL-8B-Thinking   ⏳ 工程接入完成，待本机 vLLM 实测
```

原则：

```text
Capability AVAILABLE
!=
所有 Provider 都已 QUALIFIED
```

额外本地 Provider A/B 属于后续 Provider qualification / 性能优化，不再阻塞 P8。

---

# 12. P7 / P8 边界

Seko 实测可观察链路：

```text
源作概览分析
→ 读取节点详情
→ 逐镜拉片分析
→ 分镜表
```

因此 P7 仍不输出逐 Shot：

- 景别；
- 构图；
- 运镜；
- 焦距 / 景深；
- 逐镜主体绑定；
- 逐镜对白 / 旁白列；
- 逐镜音效列。

这些属于 P8。

P8 固定输入：

```text
完整 Episode
+
CURRENT SOURCE_BIBLE
+
CURRENT SHOT_ANCHORS
+
需要时读取 CURRENT Source Evidence
↓
逐镜精细拉片
```

P8 尚未开发，但在 P7 已验收后可以作为下一独立阶段开始。
