# 复刻短剧 Root Skill 1.7

## 唯一普通主流程

```text
1. 分析视频获取分镜表
2. 分镜表本土化改写
3. 提取资产并生成真实资产图
4. 用目标视频模型对应的 Professional Skill 编译多参考音画提示词
5. 用资产图 + 提示词生成视频并人工选片
```

这五步是普通 Replica 产品的唯一主链。P11 Target Bible、P12 独立 Target Script、P14 TTS/Timing、旧 P15 Storyboard Compiler 与 P17 Post 仍保留历史数据和高级兼容能力，但不再是 MiniMax H3 原生音画主链的硬前置。

## Step 1 分镜分析

完整 Episode 仍是 Source Truth。内部可以运行 Shot Anchors、ASR/OCR、整集理解、逐镜拉片和身份归一，但对产品只交付正式 `SOURCE_SHOT_FACTS + SOURCE_VIDEO_SNAPSHOT`。分镜表必须包含 authoritative timing、镜头语言、对白和稳定人物/场景/道具身份。

## Step 2 本土化分镜

`storyboard-localization@1.0.0` 直接读取 CURRENT `SOURCE_VIDEO_SNAPSHOT`，不先要求 Target Bible / Target Script。

每个镜头：
- 画面、动作、场景和镜头理解描述使用简体中文；
- 对白使用项目 `target_language`；
- 每句目标对白同时有 `target_dialogue_zh` 中文翻译供中国用户理解；
- 中文翻译不是第二句要说出的对白；
- Shot 顺序、start/end/duration、结构化 camera facts 不变；
- Target entity id 由服务端确定性绑定，Provider 不拥有 id。

Task 成功只产生 NEEDS_REVIEW candidate；显式 ACCEPT 才发布 `TARGET_STORYBOARD v2`。

## Step 3 资产图

`asset-image-generation@1.1.0` 只读取 CURRENT `TARGET_STORYBOARD v2`，提取实际使用的人物、场景、道具。当前正式链路是：本土化资产事实 → 火山引擎 Ark / Doubao 资产视觉设计与 Flux Prompt Compiler → `flux-schnell-asset-reference-v2` → 本机 ComfyUI / Flux.1 Schnell 生成 PNG。

中文 `review_description_zh` 只用于审核，不再直接冒充图片模型执行 Prompt。真正的 `image_prompt` 必须是针对当前图片模型编译的执行提示词。Character 必须是单人、完整全身、中性参考姿态和中性棚拍背景；Scene 必须是无人空场景环境基线；Prop 必须是单一孤立道具。当前 Flux Schnell CFG=1.0，因此禁止文字、水印、拼图、重复主体、裁切主体、额外人物/物体等关键约束必须进入真实执行 Prompt，而不能只留在未实际参与采样的 negative 文本字段里。

正式资产必须有真实 `reference_media`、受管存储路径、SHA256、宽高和 ProviderJob。Prompt Compiler 与 Image Runtime 都必须留下 ProviderJob；`reference_media=[]` 不算完成。显式 ACCEPT 后发布 `TARGET_ASSETS v2`。

## Step 4 模型专属 Prompt Skill

当前视频模型为 MiniMax H3，因此固定使用：

```text
minimax-h3-prompting@1.0.0
TARGET_STORYBOARD + TARGET_ASSETS
→ GENERATION_SEGMENTS v2
```

Skill 负责：
- `<Picture 1>...<Picture N>` 参考图槽位；
- 场景、说话角色、可见角色、道具的确定性优先级；
- 目标语言原样对白；
- 中文审核翻译分离；
- 镜头、动作、环境音、SFX；
- native synchronized picture + audio；
- 时长、比例、negative constraints。

Runtime 只执行，禁止自行润色 Prompt、猜资产或改变对白。

## Step 5 MiniMax H3 生成

有 `reference_conditions` 的正式 Segment 必须走 H3 Ref2VA，多参考图片由 Prompt Skill 已经确定。ComfyUI Runtime 上传受管资产图，按同一 slot 顺序连接 `ref_image_1..N`，生成原生音画 MP4，保存到 Studio 后做 SHA256 + ffprobe Technical QC。

Technical QC PASS 不等于语义 PASS。用户必须实际播放检查人物、场景、动作、对白、声音与连续性，并显式选片后才发布正式 `GENERATED_VIDEO + GENERATION_SELECTION`。

## 新能力准入状态

```text
STORYBOARD_LOCALIZATION = PLANNED
ASSET_IMAGE_GENERATION = PLANNED
MODEL_PROMPTING = PLANNED
VIDEO_GENERATION = PLANNED
QC_SELECTION = PLANNED
```

代码完成、自动测试、ComfyUI READY、甚至成功生成 candidate 都不能改成 AVAILABLE。只有同一真实 Replica 项目按这五步完成人工验收并由用户明确确认，才允许更新正式状态。
