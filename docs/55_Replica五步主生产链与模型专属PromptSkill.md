# Replica 五步主生产链与模型专属 Prompt Skill

> 日期：2026-09-14  
> 状态：新的最高优先级产品与工程合同。  
> 本文明确替代 `docs/53`、`docs/54` 以及 `docs/49~52` 中关于 **Replica 普通用户主流程顺序** 的旧口径；历史 P0~P13 验收事实和旧 Artifact revision 仍保留，不被数据库迁移静默改写。

## 1. 用户确认的唯一主流程

```text
1. 分析视频获取分镜表
2. 分镜表本土化改写
   - 画面 / 动作 / 场景描述：简体中文，供中国用户审核理解
   - 对白：目标本土语言
   - 每句目标对白：同时提供简体中文翻译，仅供理解审核
3. 从本土化分镜提取人物 / 场景 / 道具，使用当前图片模型对应的 Professional Skill 分析分镜证据并编译模型专属资产提示词，再根据提示词生成真实资产图
4. 使用当前视频模型对应的 Professional Skill，编译模型原生多参考音画同步提示词
5. 使用资产图 + 模型专属提示词生成视频
```

普通主链不得再要求用户先经过 Target Bible、独立 Target Script、独立 TTS、Timing、旧 P15 分镜编译等产品阶段。上述能力可以作为历史兼容、诊断或高级声音模式存在，但不是 H3 原生音画主链的硬前置。

## 2. Artifact 主链

复用现有稳定 Artifact 名称，但升级 typed revision 合同：

```text
SOURCE_VIDEO_SNAPSHOT
  └─ SOURCE_SHOT_FACTS              # 第 1 步原片分镜事实
        ↓
TARGET_STORYBOARD v2                 # 第 2 步本土化分镜
        ↓
TARGET_ASSETS v2                     # 第 3 步，必须含真实资产图 reference_media
        ↓
GENERATION_SEGMENTS v2               # 第 4 步，模型专属 Prompt Skill 输出
        ↓
GENERATED_VIDEO / GENERATION_SELECTION
```

`TARGET_STORYBOARD v2` 在 `TARGET_ASSETS` 之前成立；因此新合同禁止 `TARGET_STORYBOARD` 反向依赖 `TARGET_ASSETS`。

## 3. 本土化分镜合同

硬输入只有 CURRENT `SOURCE_VIDEO_SNAPSHOT` 与项目目标地区配置。服务端从 Snapshot 中读取正式 Shot Facts、稳定人物/场景/道具和 canonical dialogue。

当前 Step 2 Runtime 固定直接使用火山引擎 Ark / Doubao，不继承 Step 1 的 `source_understanding_provider`。因此即使原片理解选择本地 Qwen，本土化分镜仍通过火山引擎执行。当前默认模型为 `doubao-seed-2-1-pro-260628`，沿用已配置的 Ark endpoint 与凭据。

每个 Shot 必须保留：

- source shot anchor / shot number；
- authoritative start / end / duration；
- source camera language；
- source visual description；
- 目标人物 / 场景 / 道具稳定 ID；
- `localized_visual_description_zh`：中文本土化画面描述；
- `camera_description_zh`：中文镜头理解说明；
- 目标语言对白；
- `target_dialogue_zh`：目标对白的中文翻译，只用于审核，禁止作为 H3 要说出的对白。

Provider 不拥有 Artifact ID、target entity ID、时间轴或 source identity；这些由服务端确定性绑定。

## 4. 资产图合同

第 3 步只消费 CURRENT `TARGET_STORYBOARD v2`，从实际分镜使用实体中提取 Character / Scene / Prop。

正式执行顺序固定为：

```text
CURRENT TARGET_STORYBOARD v2
→ 提取实际使用的 Character / Scene / Prop
→ 当前图片模型对应 Professional Skill 分析该资产的本土化分镜证据
→ 编译 image_prompt / negative_prompt
→ Image Runtime 严格执行已编译提示词
→ 真实 reference_media
```

禁止把人物卡长描述、人物关系、整段剧情说明直接拼进图片模型 Prompt。人物的“某人的丈夫 / 妻子 / 同事”等叙事关系只能作为上游语义事实存在；除非资产合同本身要求多人，否则不得因此在单人物资产图里生成第二个人。

正式 `TARGET_ASSETS v2` 必须：

- 每个被分镜引用的 Target entity 都有稳定 target_asset_id；
- 有中文可审核视觉定义；
- 至少有一张真实、已持久化、带 SHA256 和尺寸的 `reference_media`；
- 图片由真实 Image Runtime 生成，不允许 `reference_media=[]` 冒充完成；
- 当前 Windows 默认使用本机 ComfyUI + `z_image_turbo_bf16.safetensors`；其模型专属 Prompt Skill 为 `z-image-turbo-asset-prompting@1.2.0`，CLIP 为 `qwen_3_4b.safetensors`、VAE 为 `ae.safetensors`；
- 人物资产固定是一张生产参考板：**正面全身 + 侧面全身 + 背面全身 + 面部特写**。禁止把四格结构交给图片模型一次自由排版；Runtime 必须分别生成正面/侧面/背面单人全身图，使用同一身份 Prompt 与同一 base seed，再从正面图确定性裁出面部特写并固定合成四格参考板；每个模型分支都使用“单张全身棚拍、画面只出现一个人物”的措辞，禁止在模型执行文本中出现 `character reference`、复数 `views`、`turnaround`、`multi-panel`、`collage`、`contact sheet` 等容易诱发缩略多人排版的词；Prompt Skill 1.2 起连否定句也不再输出这些版式词，Runtime 对旧 Prompt 只做版式词兼容清理而不改人物身份；禁止四个全身方向、单张情绪肖像 / 情侣图 / 剧情场景图；
- 场景资产是隔离人物后的环境身份参考图；道具资产是隔离环境和无关人物后的道具身份参考图；
- 候选必须人工确认后才能成为 CURRENT TARGET_ASSETS。

历史 `TARGET_ASSETS v1` 的 text-only 资产仍可回看，但不能作为新 H3 Ref2VA 主链的资产图输入。

## 5. 模型专属 Prompt Skill

提示词生成必须经过当前视频模型对应的 Professional Skill，禁止通用字符串拼接器假装覆盖所有模型。

当前默认：

```text
MiniMax H3
→ minimax-h3-prompting@1.0.0
→ GENERATION_SEGMENTS v2
```

未来切换 Veo / Kling / Seedance 等模型时，只替换对应 Prompt Skill + Runtime Adapter；本土化分镜和资产合同不改变。

H3 Skill 每个 Generation Segment 至少输出：

- execution_prompt；
- negative_prompt；
- target-language spoken dialogue；
- native synchronized audio / ambience / SFX rules；
- camera/action/continuity；
- output ratio / duration；
- `reference_conditions[]`；
- `reference_conditions` 明确 Picture slot 1..9、target asset、reference media、role；
- execution prompt 使用 `<Picture 1>` ... `<Picture N>` 精确引用对应图片。

中文对白翻译只用于审核 UI，不得进入“演员说出”的文本。

## 6. H3 Ref2VA 音画同步执行合同

当前 Windows 本地 Runtime：ComfyUI `http://127.0.0.1:8188`。

已确认本机存在 MiniMax H3 原生节点和 FL2VA / Ref2VA 权重。新主链只要 Shot 有正式资产图，就优先使用 `MiniMaxH3ReferenceToVideo` + Ref2VA。正式 Generation Segment 必须使用 `NATIVE_AUDIO_VIDEO`，并且 `requires_lip_sync = false`：对白、环境声和音效由 MiniMax H3 在视频生成阶段原生同步生成，不先生成 IndexTTS 音频，也不再通过独立 Lip Sync 把声音贴回视频。

Runtime 的职责仅为：

1. 把 Studio 管理的正式资产图上传到 ComfyUI input；
2. 按 Prompt Skill 已确定的 Picture slot 连接 `ref_image_1..N`；
3. 把目标语言对白、环境声、音效规则与镜头动作作为 H3 原生音画提示词执行；
4. 执行模型并直接得到带同步音轨的 MP4；
5. SHA256 / ffprobe / Technical QC；
6. 进入人工选片。

Runtime 不得自行重写 prompt、猜 reference asset、改对白，或把旧 P14 `TARGET_AUDIO / TIMING` 静默插回普通主链。

### 默认启动器边界

`start.cmd` / `start.sh` 的普通 Studio 启动器只启动 Web 产品所需的 backend + frontend，不再自动启动、等待或依赖 IndexTTS 2.5。IndexTTS 的历史脚本与代码可以继续保留，用于旧 P14 数据回看、兼容测试或未来显式高级配音模式，但它不是 Replica 五步主链运行时，也不得因为旧兼容模块存在而占用普通启动时的 GPU / 内存。

如果旧版本启动器遗留了本仓库拥有的 IndexTTS 进程，生命周期清理器可以在升级后的首次启动时清掉该 orphan；清理历史进程不等于新主链启动或使用 IndexTTS。

## 7. Capability 与验收状态

新增工程 capability：

```text
STORYBOARD_LOCALIZATION = PLANNED
ASSET_IMAGE_GENERATION   = PLANNED
MODEL_PROMPTING          = PLANNED
VIDEO_GENERATION         = PLANNED
QC_SELECTION             = PLANNED
```

完成代码、自动测试、ComfyUI readiness 或生成 candidate 都不等于 AVAILABLE / PASS。必须在同一真实 Replica 项目上完成：本土化分镜人工审核、真实资产图审核、H3 Prompt 审核、真实 Ref2VA 音画视频播放审核后，用户明确确认，才能更新状态。

## 8. 历史兼容

- P11 Target Bible / P12 Target Script / P14 TTS + Timing / 旧 P15 typed revision 保留可读；
- 旧数据不得迁移成新 v2 数据后声称已经验收；
- 新普通主链不得静默调用这些旧阶段作为硬输入；
- IndexTTS 仅保留为显式历史兼容 / 可选高级声音能力，默认统一启动器不得自动拉起；
- 高级独立配音可以在后续作为可选 overlay 重新接入，但不得改变本五步主链。
