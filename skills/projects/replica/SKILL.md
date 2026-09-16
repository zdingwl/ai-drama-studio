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

`asset-image-generation@1.4.0` 只读取 CURRENT `TARGET_STORYBOARD v2`，提取实际使用的人物、场景、道具。提取后不能直接把人物卡/场景说明字符串拼进图片模型，而是必须把该资产及其实际引用镜头证据交给当前图片模型对应的 Professional Prompt Skill。

当前 Windows 图片模型绑定为：

```text
提取资产 + 本土化分镜证据
→ z-image-turbo-asset-prompting@1.4.0
→ image_prompt / negative_prompt
→ 本机 ComfyUI + z_image_turbo_bf16.safetensors → 正面 canonical master
→ qwen-image-edit-character-asset-prompting@1.0.0
→ qwen_image_edit_2511_fp8mixed.safetensors → 同身份侧面 / 背面
→ PNG reference_media
```

人物资产固定是一张横向生产参考板：**正面全身 + 侧面全身 + 背面全身 + 面部特写**。结构不能交给模型一次自由排版：Runtime 只让 Z-Image 自由生成一次正面全身 canonical master；随后把这张真实正面图作为 `Image 1` 交给 Qwen Image Edit 2511，按 Qwen 专属 Skill 锁定脸、年龄、发型、体型、上下装和鞋履，只改变朝向得到侧面/背面；面部特写直接从正面主图裁出，最后固定合成四格参考板。人物关系等叙事事实不得自动变成额外人物。

正式资产必须有真实 `reference_media`、受管存储路径、SHA256、宽高和 ProviderJob。`reference_media=[]` 不算完成。生成完成后由服务端校验 `reference_media` 完整性与 CURRENT `TARGET_STORYBOARD` lineage；校验通过即自动发布 `TARGET_ASSETS v2`，普通用户不再执行整批“确认资产图”。用户直接检查结果，发现问题时显式重新生成或使用后续单资产重做能力纠正。

## Step 4 模型专属 Prompt Skill

当前视频模型为 MiniMax H3，因此固定使用：

```text
minimax-h3-prompting@1.1.0
TARGET_STORYBOARD + TARGET_ASSETS
→ GENERATION_SEGMENTS v2
```

Skill 负责：
- `<Picture 1>...<Picture N>` 参考图槽位；
- 人物身份优先：每个可见人物先绑定 FACE + 正面 FULL_BODY，同一人物两张图强制 identity lock；画外音人物不因为对白而占视觉参考槽；场景、道具只使用剩余槽位；
- 目标语言原样对白；
- 中文审核翻译分离；
- 镜头、动作、环境音、SFX；
- native synchronized picture + audio；
- 时长、比例、negative constraints。

Runtime 只执行，禁止自行润色 Prompt、猜资产或改变对白。

## Step 5 MiniMax H3 生成

有 `reference_conditions` 的正式 Segment 必须走 H3 Ref2VA，多参考图片由 Prompt Skill 已经确定。人物不得把整张四栏审核参考板直接作为唯一 H3 输入：Step 3 会从参考板确定性持久化独立 FACE + 正面 FULL_BODY 媒体，Step 4 为每个可见人物优先占用这两个 Picture slots。ComfyUI Runtime 上传受管资产图，逐槽校验 target entity / role / SHA256 / storage path，并按同一 slot 顺序连接 `ref_image_1..N`，生成原生音画 MP4，保存到 Studio 后做 SHA256 + ffprobe Technical QC。

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
