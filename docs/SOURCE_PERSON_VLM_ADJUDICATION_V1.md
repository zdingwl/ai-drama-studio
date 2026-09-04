# LocalSubject 多人画面自动裁决 V1

## 目标

解决第一层 `Character V10.1 Candidate -> FinalCharacter` 硬解析仍无法处理的 **单镜多人 / 多镜始终多人同框** 问题。

正式链路：

```text
Breakdown LocalSubject.appearance
        ↓ 仅作弱语义 Evidence
LocalSubject 出现 Shot 集合
        ↓
Character V10.1 CharacterTrack
        ↓
V10.1 Candidate / ReID 跨镜身份集合求交
        ↓
2..6 个仍然歧义的 Candidate
        ↓
从 representative frame 按 V10.1 bbox 裁 Person Crop
        ↓
Qwen3-VL-4B-Instruct 闭集 SELECT / ABSTAIN
        ↓
>= 0.90 且 Candidate -> 唯一 FinalCharacter
且现有 Final ShotCharacterBinding 覆盖全部 LocalSubject Shot
        ↓
自动写 source_person_mappings_v1 + AssetRevision
```

## 不做什么

- 不重新运行 YOLOX Person Detection。
- 不重新运行 MOT / YoutuReID / SFace。
- 不让 Qwen 创建 Character、Candidate 或 Binding。
- 不使用对白、姓名、人物关系、剧情角色、动作、表情、左右站位猜身份。
- 不把 LocalSubject 外观描述当身份真值。

`V10.1 Person Crop/ReID` 的含义是：候选集合和跨镜人物身份来自 **已经完成的 V10.1 Track/ReID 结果**，Qwen 只负责在这些现有 Candidate 的 Person Crop 中做视觉闭集裁决。

## Fail-closed 规则

以下任一情况保持 `REVIEW`：

- 候选少于 2 个或多于 6 个；
- LocalSubject 没有稳定外观描述；
- 任一 Candidate 没有唯一对应当前 FinalCharacter；
- 当前 Final ShotCharacterBinding 未覆盖 LocalSubject 全部 Shot；
- 无法从 V10.1 representative frame 取得 Person Crop；
- Qwen 返回未知 candidate_id / 非法 JSON / ABSTAIN；
- Qwen confidence < 0.90；
- 两个 LocalSubject 在重叠 Shot 中被分给同一个 Candidate / FinalCharacter；
- Qwen 推理期间人物事实被用户或其他任务修改。

## Runtime

默认复用 Breakdown G1/P2 已安装的：

```text
Qwen/Qwen3-VL-4B-Instruct
.runtime/TransVLM/inference/pretrained/Qwen3-VL-4B-Instruct
```

默认继承 `AI_DRAMA_P2_VLM_*`；人物裁决可用以下变量单独覆盖：

```text
AI_DRAMA_PERSON_VLM_MODEL
AI_DRAMA_PERSON_VLM_MODEL_PATH
AI_DRAMA_PERSON_VLM_PYTHON
AI_DRAMA_PERSON_VLM_RUNNER
AI_DRAMA_PERSON_VLM_DEVICE
AI_DRAMA_PERSON_VLM_MAX_NEW_TOKENS
```

## 缓存

Qwen 规范化裁决按 fingerprint 缓存到项目 workspace。fingerprint 包含：

- LocalSubject anchor / appearance；
- 当前 Character V10.1 Run；
- Candidate / FinalCharacter 对应；
- Track ID / representative bbox /时间等事实；
- Provider profile / model。

同一事实重复打开人物确认不会重复调用 Qwen；上游 Breakdown、Character Run、Track 或候选事实变化后 fingerprint 自动变化，旧裁决不会继续使用。

缓存只保存规范化 `SELECT/ABSTAIN` 结果，不保存 prompt 和模型原始 chatter。
