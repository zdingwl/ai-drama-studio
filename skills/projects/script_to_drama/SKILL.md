# 剧本生成短剧 Root Skill（1.2）

## 业务目标与工程边界

从原剧本生成短剧，独立执行：`SOURCE_TEXT → SCRIPT_ANALYSIS → SOURCE_TEXT_SNAPSHOT / STORY_SKELETON / RHYTHM_SKELETON → TARGET_BIBLE / TARGET_ASSETS（定义） → TARGET_ASSET_IMAGES（正式参考图） → TARGET_STORYBOARD（导演分镜） → GENERATION_SEGMENTS（MiniMax H3 模型专属 Prompt） → GENERATED_VIDEO（待审镜头） → GENERATION_SELECTION（人工确认） → FINAL_OUTPUT（FFmpeg 成片）`。

**工程入口已接通，不等于真实图片/视频模型已完成出片验收。** 用户需配置所选图片、文本和 H3 Provider，并在同一实际项目检查人物一致性、画面、对白/音轨、镜头衔接及成片质量；未通过前不得把该能力宣传为已完成真实端到端验收。

## 输入和复用边界

- 复用 `SOURCE_TEXT` 不可变上传、版本失效、Artifact Graph、任务/ProviderJob 和 `script_localization.long_text` 无损分块；保留自己的项目类型授权、业务服务与修订数据。
- 分析阶段沿用经登记的 `script-analysis`；目标世界和导演分镜分别执行 `script-world-design` 与 `script-storyboard-directing`。
- 资产图通过现有图片模型专属 Prompt Skill 及图片 Runtime 执行；人物优先生成稳定主身份图并从正式人物参考板拆出面部、正面参考。复用模型底层适配器，不直接读写 Replica 专属版本表或放宽 Replica 接口。
- 视频阶段通过模型专属 `minimax-h3-prompting` 和 H3 Runtime；参考图槽位连续且不超过当前合同上限，正式分段输出须通过文件校验、ffprobe 与时长校验。
- 只有用户明确确认全部待审分段后才能发布正式选片；FFmpeg 从当前正式选片合成 H.264/AAC MP4，媒体读取只认该项目当前正式版本。

## 不可妥协的业务规则

原剧本是 Source Fact；非原文事实的视觉补足属于 Visual Inference，剧情歧义交人工决定。源文本按自然场次/段落分段，跨段共用人物/场景/道具 registry；分段输出必须精确覆盖、引用逐字可查、实体 ID 有效，禁止静默截断。上游版本变更后旧下游必须过期，重新生成不得回退到旧媒体。失败时保留有效分段的检查点，不得发布残缺产物。

图片 Prompt 必须服从用户确认的视觉身份，模型执行由 Runtime 负责，不能把 Skill 当成图片或视频模型本身。素材模型未就绪、参考图超限、输出不完整、文件缺失或未确认选片时应明确失败，不得使用空参考或 Replica 专属产物伪造成功。

## 参考依据

- Final Draft 剧本元素：https://kb.finaldraft.com/hc/en-us/articles/27646947570196-What-are-script-elements
- StudioBinder 剧本拆解：https://www.studiobinder.com/tutorials/breakdown/intro-to-script-breakdowns/
- Adobe 镜头清单：https://www.adobe.com/uk/creativecloud/video/discover/shot-list.html
- Adobe 镜头连续性：https://www.adobe.com/creativecloud/video/production/cinematography/camera-shots-and-angles/sequence-shot.html
- Runway 视频提示编排：https://help.runwayml.com/hc/en-us/articles/48324313115155-Image-to-Video-Prompting-Guide

以上资料提供剧本元素、拆解与镜头编排思路；**具体模型输入/参考图、Prompt 长度、图片和视频质量的有效性必须以所选模型正式合同和真实项目验收为准**，不从上述通用资料推断供应商未承诺的能力。

## 验收标准

工程验收：项目类型隔离、完整分段/资产/镜头覆盖、模型字段适配、任务续跑、版本失效、人工确认门禁、媒体 hash、真实本机 FFmpeg 拼接和前后端回归。真实验收：在同一剧本项目跑通正式图片与视频 Provider，人工检查身份/空间/动作/对白/音轨/成片，记录失败用例并修复后再标记为完整可用。
