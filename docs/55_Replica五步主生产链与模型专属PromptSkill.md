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

目标对白时长适配属于第 2 步，不得推迟到 H3 Prompt 或视频生成阶段。每条 canonical utterance 必须把权威 start/end/duration 和宽松语速预算交给本土化 Provider；目标语口语按英文每秒最多 4 词、CJK 每秒最多 6 字进行文本预检。文本估算允许固定 0.15 秒 ASR 边界容差，仅用于极短单音节对白，不得放宽实质性超时。直译超时时必须在不改变剧情信息、语气和人物关系的前提下缩写为自然目标语对白。未通过时长预检的结果不得形成可审核候选；人工编辑保存也必须执行同一校验。H3 阶段只做只读复核，不得自动改句或用加速指令伪造合格。

长剧集本土化必须按 Episode 和跨镜 utterance 边界分批，禁止一个 Provider 批次同时混入两集，也禁止把同一句跨镜对白切到两个批次分别本土化。首次出现的人物、场景和道具目标名称形成任务内冻结 Identity Registry；后续批次必须逐字复用，不得出现 Riley/Rachel/Rae、Jake/Jude 或家庭姓氏漂移。时长或身份名称校验失败时，同一 Task 最多做两次定向修正；每次远端请求必须单独先持久化 ProviderJob。每批已验证 semantic 必须写入 Task checkpoint，中断恢复不得重跑已完成的付费批次。

TARGET_STORYBOARD 必须分别记录 visual projection fingerprint 与 dialogue projection fingerprint。如果新 revision 仅修改对白/时长且 visual projection 逐字未变，服务端应确定性复用已持久化的真实资产媒体并发布新 lineage 的 TARGET_ASSETS，不得再调用图片 Runtime；H3 提示词和视频结果仍必须因对白变化而 STALE。多窗口编辑候选必须使用 candidate content fingerprint 乐观锁，禁止静默后写覆盖先写。

## 4. 资产图合同

第 3 步只消费 CURRENT `TARGET_STORYBOARD v2`，从实际分镜使用实体中提取 Character / Scene / Prop。

正式执行顺序固定为：

```text
CURRENT TARGET_STORYBOARD v2
→ 提取实际使用的 Character / Scene / Prop
→ Character 先执行 character-visual-design，将正式人物语义与分镜外观证据冻结为 CharacterVisualDesignPacket
→ 当前图片模型对应 Professional Skill 只消费上游视觉合同并编译模型专属 Prompt
→ 编译 image_prompt / negative_prompt
→ Image Runtime 严格执行已编译提示词
→ 真实 reference_media
```

禁止把人物卡长描述、人物关系、整段剧情说明直接拼进图片模型 Prompt。人物的“某人的丈夫 / 妻子 / 同事”等叙事关系只能作为上游语义事实存在；除非资产合同本身要求多人，否则不得因此在单人物资产图里生成第二个人。

Character 的稳定脸型、五官、发型、肤色、体态、服装和识别点必须先由 `character-visual-design@1.1.0` 形成可审计 `CharacterVisualDesignPacket`。图片模型 Prompt Skill 不得绕过该包重新从人物关系、姓名或常识猜测身份细节。Step 3 的硬输入仍只有 CURRENT `TARGET_STORYBOARD v2`；如果存在 CURRENT `TARGET_BIBLE`，仅允许作为附加稳定身份约束，缺失时不得阻断五步主链。

正式 `TARGET_ASSETS v2` 必须：

- 每个被分镜引用的 Target entity 都有稳定 target_asset_id；
- 有中文可审核视觉定义；
- 至少有一张真实、已持久化、带 SHA256 和尺寸的 `reference_media`；
- 图片由真实 Image Runtime 生成，不允许 `reference_media=[]` 冒充完成；
- 当前 Windows 场景/道具及人物正面 master 默认使用本机 ComfyUI + `z_image_turbo_bf16.safetensors`；主 Prompt Skill 为 `z-image-turbo-asset-prompting@1.5.0`，整体资产 Prompt Contract 为 `replica-assets-zimage-clean-positive-v5`，Z-Image CLIP 为 `qwen_3_4b.safetensors`、VAE 为 `ae.safetensors`；正向提示词只包含目标视觉身份与正向构图，`negative_prompt` 独立保存且不再拼入 Z-Image 正向编码；人物侧面/背面固定使用 `qwen-image-edit-character-asset-prompting@1.0.0` + `qwen_image_edit_2511_fp8mixed.safetensors` + `qwen_2.5_vl_7b_fp8_scaled.safetensors` + `qwen_image_vae.safetensors`；
- 人物资产固定是一张生产参考板：**正面全身 + 侧面全身 + 背面全身 + 面部特写**。禁止把四格结构交给图片模型一次自由排版；Runtime 只允许 Z-Image 自由生成一次唯一正面全身 canonical master，然后把该真实正面图作为 Qwen Image Edit 的 `Image 1`。侧面和背面不得再独立文生图，也不得用同 seed 相似性冒充身份锁定；Qwen 专属 Skill 必须锁定同一人的脸、年龄、发型、肤色、体型、上装、袖长、下装类型/长度、花纹/颜色以及鞋履存在/类型/颜色，只允许改变朝向。面部特写直接从正面主图确定性裁出，再固定合成四格参考板；禁止单张情绪肖像 / 情侣图 / 剧情场景图；
- 四栏人物参考板是人工审核表面，不得作为 H3 唯一人物输入。Runtime 必须从该确定性参考板额外持久化独立 `FACE` 与正面 `FULL_BODY` reference media（复用同一次真实生成 ProviderJob provenance）；H3 Ref2VA 人物身份只能使用这些独立媒体，禁止退化为把四栏拼图当成一张 full-body 身份图；
- 场景资产是隔离人物后的环境身份参考图；道具资产是隔离环境和无关人物后的道具身份参考图；
- 真实资产图生成完成后，服务端必须先完成 `reference_media` 完整性与 CURRENT `TARGET_STORYBOARD` lineage 校验；校验通过即自动发布为 CURRENT `TARGET_ASSETS`，普通用户不再额外执行整批“确认资产图”。用户在资产页直接检查结果，发现问题时使用重新生成 / 后续单资产重做能力纠正。

历史 `TARGET_ASSETS v1` 的 text-only 资产仍可回看，但不能作为新 H3 Ref2VA 主链的资产图输入。
图片模型或图片 Prompt Skill 的版本变化只记录 provenance，不得单独使已有真实资产图失效或强迫整批重绘。Step 4 以当前采用的、已持久化并校验 SHA256 的 reference media 为准；可见人物仍必须具备独立 `FACE` 与正面 `FULL_BODY` 参考图，缺图、文件损坏、hash 不符或实体绑定不符时必须 fail closed。人物一致性检测结果作为审核警告保留，不能仅因检测失败而阻断已有真实图片进入 H3。

## 5. 模型专属 Prompt Skill

提示词生成必须经过当前视频模型对应的 Professional Skill，禁止通用字符串拼接器假装覆盖所有模型。

当前默认：

```text
MiniMax H3
→ minimax-h3-prompting@1.1.0
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
- reference slot 采用人物身份优先：每个 `target_character_ids` 中的可见人物先固定占用 `FACE` + 正面 `FULL_BODY` 两个槽位，并在 execution prompt 中声明为同一人物，锁定脸型五官比例、年龄感、发型发色、肤色、体态和基础服装身份；场景 `LAYOUT` 与道具 `DETAIL` 只能使用剩余槽位；
- 画外音 / 旁白说话人如果不在 `target_character_ids`，不得仅因 dialogue 而上传人物图片，避免 Ref2VA 引入额外人物或跨角色特征混合；

中文对白翻译只用于审核 UI，不得进入“演员说出”的文本。

## 6. H3 Ref2VA 音画同步执行合同

当前 Windows 本地 Runtime：ComfyUI `http://127.0.0.1:8188`。

已确认本机存在 MiniMax H3 原生节点和 FL2VA / Ref2VA 权重。新主链只要 Shot 有正式资产图，就优先使用 `MiniMaxH3ReferenceToVideo` + Ref2VA。正式 Generation Segment 必须使用 `NATIVE_AUDIO_VIDEO`，并且 `requires_lip_sync = false`：对白、环境声和音效由 MiniMax H3 在视频生成阶段原生同步生成，不先生成 IndexTTS 音频，也不再通过独立 Lip Sync 把声音贴回视频。

Runtime 的职责仅为：

1. 把 Studio 管理的正式资产图上传到 ComfyUI input；
2. 对每个 Picture slot fail-closed 校验 `target_asset_id / target_entity_id / role / reference_id / SHA256 / storage path` 与 CURRENT TARGET_ASSETS 完全一致，再按 Prompt Skill 已确定的顺序连接 `ref_image_1..N`；
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

完成代码、自动测试、ComfyUI readiness 或生成 candidate 都不等于 AVAILABLE / PASS。必须在同一真实 Replica 项目上完成：本土化分镜人工审核、真实资产图可视检查（无需单独确认按钮）、H3 Prompt 审核、真实 Ref2VA 音画视频播放审核后，用户对整条真实链路明确确认，才能更新状态。

## 8. 历史兼容

- P11 Target Bible / P12 Target Script / P14 TTS + Timing / 旧 P15 typed revision 保留可读；
- 旧数据不得迁移成新 v2 数据后声称已经验收；
- 新普通主链不得静默调用这些旧阶段作为硬输入；
- IndexTTS 仅保留为显式历史兼容 / 可选高级声音能力，默认统一启动器不得自动拉起；
- 高级独立配音可以在后续作为可选 overlay 重新接入，但不得改变本五步主链。
# 视觉资产工作台交互补充（2026-09-17）

## H3 输入审计补充（2026-09-18）

- H3 生成命令必须显式指定当前 episode_id，任务持久化剧集范围；worker 仅编写该集。单集重新生成按相同上游 lineage 合并保存，其他集内容及其生成来源保留；读取与页面任务状态按当前剧集隔离。旧无剧集范围任务不得继续执行全项目生成。

- 跨镜重叠对白不得在各独立音画生成段重复要求完整说出；按 episode + utterance id 检查重复，出现重复必须先修订生成分段。
- 文本语速估算只作明显超时预检，不等于真实音频时长或人工听审。宽松上限按英文每秒 4 词、CJK 每秒 6 字；超时问题必须在 H3 页面明确警示，并在进入视频生成前 fail closed，不能通过加速指令假装合格。H3 Prompt 可先完成并保留，供用户定位需要回到本土化分镜修订的对白。
- H3 编写 Provider 必须收到相对本段的对白起止时间；场景、道具超过 9 个参考槽不得静默遗漏。
- FACE 搭配 FULL_BODY 或 FULL_BODY_FRONT 均为合法人物身份对。
- 旧提示词 GET 只读返回审计问题，不改写历史结果；视频入口再次执行预检。任务成功仅表示生成已完成，不代表当前内容可用于视频。
- 原片镜头时间仅作为不可变溯源事实；本土化分镜必须按目标动作、镜头节奏和目标对白重新规划连续的目标时间轴，不得把原片时长直接当作目标成片时长。
- 本土化分镜不继承 H3 等单一视频模型的单次生成时长上限；模型专属 Prompt Skill 负责把较长目标镜头切成可执行分段，且不得切断已规划的对白窗口。
- 重新规划产生新的 `NEEDS_REVIEW` 候选，不自动覆盖已确认版本；涉及节奏与对白的修订继续保持人工审核边界。


普通用户的视觉资产阶段必须拆分为以下显式操作，不得再以一次命令同时完成提取、提示词编写和全部出图：

```text
空白工作台
→ 用户点击“提取资产”
→ 展示本土化分镜实际引用的人物 / 场景 / 道具
→ 用户单选或多选资产
→ Character Visual Design Skill（人物）+ 模型专属 Prompt Skill 生成所选资产提示词
→ 用户单选或多选已有提示词的资产
→ 图片任务进入持久化队列，严格逐个调用本地图片 Runtime
→ 每个资产完成后立即显示并自动采用最新结果
```

硬规则：

- GET 页面加载保持零写入，未显式提取时工作台为空；
- 提取只读取 CURRENT 本土化分镜，确定性形成实体工作集，不调用 Provider；
- 提示词生成必须读取对应实体定义、逐镜证据、Professional Skill、模型绑定和模型专属 Prompt Skill，不允许前端字符串拼接；
- 提示词和图片命令必须携带明确选择的 `target_asset_id` 集合；
- 图片 Provider 调用前必须先持久化 Task 和 ProviderJob；同一 Task 内严格一次只生成一个资产，前一个完成并持久化后才开始下一个；
- 图片生成成功即自动成为该资产当前采用结果，无需额外“确认”按钮；
- 同一资产多次生成必须追加 generation history，不得覆盖旧媒体；
- 只有工作集中全部资产均有当前采用图片时，才自动发布完整 CURRENT `TARGET_ASSETS`，部分完成状态只属于工作台，不能冒充完整正式资产集；
- 用户未来显式修改提示词或选择旧图片时，应产生新的工作台 revision/选择记录；不得反写本土化分镜或 Source Truth。
