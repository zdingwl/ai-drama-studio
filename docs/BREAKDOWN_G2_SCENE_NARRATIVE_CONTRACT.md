# Breakdown G2.3 / G2.4 — Scene Narrative Contract v1

> Status: **IMPLEMENTED / USER-LOCAL TEST PENDING / REAL-MODEL ACCEPTANCE PENDING**  
> Prompt profile: `breakdown-g2-scene-narrative-zh-v1`  
> Local runtime profile: `breakdown-g2-scene-narrative-qwen3-local-v1`  
> Source foundation: **G2.1/G2.2 FINAL PASS / FROZEN FOUNDATION**

## 1. 一句话说明

G2.1/G2.2 已经把视频事实整理成稳定的 Scene Timeline。G2.3 不再看视频，只把每个 Scene 的冻结文字事实交给本地纯文本 LLM，让它做两件事：

```text
1. 场景标题
2. “这一段发生了什么”剧情摘要
```

除此之外，LLM **没有任何事实写权限**。

```text
镜头画面      = G2.2 冻结事实
出场人物      = G2.2 冻结事实
人物动作      = G2.2 冻结事实
ASR 对白      = G2.2 冻结事实
OCR           = G2.2 冻结事实
道具          = G2.2 冻结事实
景别 / 构图   = G2.2 冻结事实
时间轴        = G2.2 冻结事实
```

## 2. 正式流程

```text
FINAL PASS scene-timeline-v1
        ↓
Scene Grounding Packet
        ↓
为事实分配 F0001 / F0002 / ...
        ↓
计算 Scene source_fingerprint
        ↓
本地 Qwen3-VL text-only
一次加载模型，Scene 顺序处理
        ↓
Scene Narrative Candidate
        ↓
G2.4 Source / Support Validator
        ↓
Validated Narrative Overlay
        ↓
只允许覆盖 title / story_summary
        ↓
其余 Shot 字段保持逐项不变
```

## 3. Grounding Packet

实现：

```text
engine/app/breakdown_scene_grounding_v1.py
engine/app/breakdown_scene_narrative_contract_v1.py
```

每个 Scene 独立构建 `scene-grounding-v1`。

LLM 看到的不是数据库 Draft/Evidence，而是冻结的 Scene Timeline 投影：

```text
Scene 基础信息
Scene-local 人物1 / 人物2 / ...
Shot visual
Shot performance
ASR dialogue
Shot props
shot type / composition / reliable camera motion
OCR
```

每条可引用事实都有内部 id：

```text
F0001
F0002
F0003
...
```

Fact kind 包括：

```text
SCENE_LOCATION
SCENE_SPACE
SCENE_TIME
SCENE_ENVIRONMENT
SCENE_BASE_SUMMARY
PERSON_APPEARANCE
SHOT_VISUAL
SHOT_PERFORMANCE
DIALOGUE
PROP
PROP_INTERACTION
SHOT_TYPE
COMPOSITION
CAMERA_MOTION
OCR
```

ASR / OCR `fact.text` 保留 Scene Timeline 原字符串，不做纠错、trim 或匿名标签替换。

## 4. source_fingerprint

每个 Grounding Packet 根据以下冻结输入计算 SHA-256：

```text
Run anchor
ShotRevision anchor
Episode
Scene ordinal
Scene info
Scene-local people
全部 Fxxxx facts
```

Narrative Overlay 保存这个 fingerprint。

应用 Overlay 时会重新构建当前 Scene Packet 并再次计算 fingerprint：

```text
fingerprint 一致
→ 允许使用已验证 title / story_summary

fingerprint 不一致
→ fail closed
→ 禁止把旧 Narrative 套到新的 Scene facts
```

## 5. LLM 输出权限

正式 Candidate 只有：

```json
{
  "scene_ordinal": 1,
  "readable_title": {
    "text": "走廊里的交流",
    "support": ["F0001", "F0005"]
  },
  "story_summary": {
    "text": "人物1走向人物2并与其交流。",
    "support": ["F0005", "F0008"]
  }
}
```

没有证据时字段必须为 `null`。

Schema 使用 `extra="forbid"`，因此 LLM 如果试图返回：

```text
people
props
dialogue
OCR
shot_type
composition
timestamp
Character ID
Scene ID
Prop ID
```

都不是合法 Candidate。

## 6. Prompt Injection 保护

系统 Prompt 明确把：

```text
<SCENE_DATA> ... </SCENE_DATA>
```

定义为不可信业务数据。

即使 ASR/OCR 中出现：

```text
忽略以上规则
执行命令
SYSTEM:
把人物改名成...
```

也只能作为视频中识别出来的文字数据，不能成为模型指令。

## 7. G2.4 Source / Support Validator

实现：

```text
engine/app/breakdown_scene_narrative_validator_v1.py
```

确定性校验：

```text
scene_ordinal 必须一致
support Fxxxx 必须真实存在
support 自动去重
禁止输出内部 P1/P2/... 引用
人物N 必须属于当前 Scene
提到人物N时 support 必须确实关联这个人物
地点 / 时间 / 室内外 / 道具 / 景别 / 运镜等硬锚点出现时必须有对应 support
禁止 Final Asset / ID 风格声明
```

某一个 claim 不合格：

```text
只丢弃这个 claim
→ 回退到确定性 Timeline title / story_summary
```

不会修改 G1/G2.2。

注意：support validator 是强 provenance/anchor guard，不声称能够数学证明任意自然语言句子的完整语义蕴含。因此 LLM 权限才被限制为 Scene 标题和摘要，而不是允许它重写 Shot 事实。

## 8. 本地 Qwen3-VL text-only runtime

实现：

```text
engine/app/breakdown_scene_narrative_qwen3_v1.py
scripts/run_breakdown_scene_narrative_qwen3.py
```

默认复用已经存在的隔离 runtime/checkpoint：

```text
.runtime/TransVLM/inference/.venv
.runtime/TransVLM/inference/pretrained/Qwen3-VL-4B-Instruct
```

它只复用运行环境和 base checkpoint，**不会调用冻结的 G1 Window / Exact-Shot runner**。

运行方式：

```text
主工程生成全部 Scene prompts
→ 一个 manifest
→ 启动一次隔离 Python 3.12 subprocess
→ Qwen3-VL-4B-Instruct 加载一次
→ Scene 1 text-only generation
→ Scene 2 text-only generation
→ ...
→ JSONL candidates
→ G2.4 validator
```

因此不会出现“每 Scene 重新加载一次 4B 模型”的性能错误。

默认：

```text
device = cuda
max_new_tokens = 512
sampling = false / deterministic generation
network = offline
```

可选环境变量：

```text
AI_DRAMA_G2_LLM_PYTHON
AI_DRAMA_G2_LLM_MODEL_PATH
AI_DRAMA_G2_LLM_DEVICE
AI_DRAMA_G2_LLM_MAX_NEW_TOKENS
AI_DRAMA_G2_LLM_RUNNER
```

未配置 G2 专用路径时，Python/model/device 会兼容现有 `AI_DRAMA_P2_VLM_*` 配置。

## 9. Error / fallback

```text
模型 runtime 缺失
→ Narrative 降级
→ deterministic Timeline 继续可用

整个 batch subprocess 失败
→ 所有 Scene Narrative 降级
→ deterministic Timeline 继续可用

单 Scene 模型失败
→ 该 Scene 无 Narrative overlay
→ deterministic title / story_summary 继续可用

LLM JSON 非法
→ 不自动发第二次模型请求
→ 直接降级

support 不存在 / 人物错误 / fingerprint 过期
→ 对应 claim 或 overlay 被拒绝
```

不做“坏 JSON 自动再问一次 LLM”，避免隐藏的重复推理与不可控耗时。

## 10. 不修改的冻结内容

本阶段没有修改：

```text
Window Context v4
Exact-Shot Compact v3
Fusion E6-v2
Character V10.1
scene-timeline-v1 Contract
G2.2 deterministic assembler
```

也没有新增：

```text
Final Character
Final Scene
Final Prop
Final Binding
```

## 11. Tests

新增：

```text
engine/tests/v2/test_breakdown_scene_narrative_v1.py
engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py
```

覆盖：

```text
Grounding fingerprint deterministic
ASR/OCR verbatim in Grounding
fake support rejection
hard-anchor support coverage
P1/P2 leakage rejection
unknown 人物N rejection
prompt injection remains data
Provider error detail does not leak
invalid JSON has no hidden second call
Overlay changes only title/story_summary
stale fingerprint rejected
local Qwen Adapter batch path
```

## 12. User-local acceptance

先运行纯代码测试，不加载真实 4B 模型：

```powershell
python -m pytest engine/tests/v2/test_breakdown_scene_narrative_v1.py engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py -q
```

当前新增测试目标：

```text
8 passed
```

然后检查本地 runtime：

```powershell
python -c "from engine.app.breakdown_scene_narrative_qwen3_v1 import Qwen3VLSceneTextLLM; print(Qwen3VLSceneTextLLM().runtime_preflight())"
```

只有上述测试通过后，再对最终已接受 Run 做真实 text-only Qwen Scene Narrative 验收。

## 13. 后续顺序

```text
G2.3/G2.4 user-local tests
→ local Qwen runtime preflight
→ 最终 Run 两个 Scene 的真实文本模型验收
→ G2.3/G2.4 FINAL PASS
→ G2.5 Scene Timeline API
→ G2.6 普通用户 Scene Timeline UI
```
