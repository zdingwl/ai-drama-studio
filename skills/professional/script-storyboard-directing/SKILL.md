# 剧本生成短剧·导演分镜 Professional Skill

## 职责

把 `SCRIPT_TO_DRAMA` 已分析的原剧本转为结构化、可审阅的 `TARGET_STORYBOARD`。这里只制作导演镜头计划；视频模型的专用 Prompt、首帧生成、音频真实时长、视频调用、选片与后期均属于后续 Runtime/Skill。

## 公开资料与方法转化

- Adobe 镜头清单：https://www.adobe.com/uk/creativecloud/video/discover/shot-list.html —— 分镜必须让摄影和剪辑明确每镜景别、视角和动作覆盖，不能只写“电影感”。
- Adobe Storyboarding：https://www.adobe.com/ca/creativecloud/video/discover/storyboarding.html —— 通过不同景别和镜头关系呈现角色与情绪，分镜是剪辑前的画面计划。
- Adobe 镜头连续性：https://www.adobe.com/creativecloud/video/production/cinematography/camera-shots-and-angles/sequence-shot.html —— 动作衔接、屏幕方向、视线与 180 度轴有助于避免连续性错误；越轴可以有意设计但不能无解释跳变。
- Adobe 分镜要素：https://www.adobe.com/uk/acrobat/resources/how-to-make-a-storyboard.html —— 逐镜编号、动作、摄影机方向、对白/旁白、预估时长可帮助形成可执行清单。
- Runway 图生视频提示：https://help.runwayml.com/hc/en-us/articles/48324313115155-Image-to-Video-Prompting-Guide —— 首帧定义画面风格和构图，视频提示优先描述主体动作、环境运动和摄影机运动；这里保留这些分开的字段，由下游模型专属 Prompt Skill 编译。

外部资料用于分镜制作方法；源证据锁、可追溯 Artifact 和人工审批是本系统自己的工程约束。

## 分镜流程

1. 用稳定 `source_chunk_index`、场次号或源文本锚点锁定待拍段落。必须看见原文的完整事件，不能只读整个剧本的摘要来猜镜头。
2. 对每个连续情节确定视觉信息的最小充分镜头组：建立空间的镜头、关键行动、角色反应、信息揭示及场景结束的切换镜头。不能强迫所有场次采用同一套景别模板。
3. 每镜填写：`shot_id`、`source_chunk_index`、`scene_number`、`narrative_beat`、`character_ids`、`scene_id`、`prop_ids`、`shot_size`、`angle`、`composition`、`camera_motion`、`visible_action`、`dialogue_or_voiceover`、`estimated_seconds`、`continuity_notes`。
4. 一个镜头只包含时间与空间上连续且可生成的动作；多次切镜、突然换地点、需要不同参考首帧的情节分成不同镜头。
5. 在两人对话中注意视线与左右方向；人物出入画、关键道具持有者、伤痕/服装/发型等状态沿镜头顺序连续。若有意跳切或越轴，注明原因。
6. 预估时长只用于规划，真实 TTS 音频与模型实际可生成片长会在后续 Timing 阶段重新校验；不要向用户声称本阶段已制作可播放成片。
7. 输出 source coverage 清单：每个处理过的原文分段应有至少一条对应镜头。尚不能结构化覆盖的重要情节记录人工检查项，不得以缺失段落的“完成”状态冒充完整剧本。

## 不允许

- 为了易生成而擅自改变结局、核心人物关系、重要对白和因果；
- 给人物/场景/道具使用不存在于目标世界 registry 的 ID；
- 以抽象心理状态取代可见动作；
- 把预估镜头时长写成真实音频 duration；
- 在分镜 Skill 内绕过模型专属 Prompt Skill，直接编造视频模型参数；
- 因模型输出截断而静默丢掉最后几场。

生成前必须做 schema、来源覆盖、实体 ID、镜头编号与依赖版本校验。