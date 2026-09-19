# 剧本生成短剧 Root Skill（1.1）

## 业务目标与当前执行边界

目标是从原剧本完成短剧；目前**已接通的预制作链**为：`SOURCE_TEXT → SCRIPT_ANALYSIS → SOURCE_TEXT_SNAPSHOT / STORY_SKELETON / RHYTHM_SKELETON → TARGET_BIBLE / TARGET_ASSETS（定义） → TARGET_STORYBOARD（导演计划）`。

现阶段尚未接通的是：资产图片与首帧生成、模型专属 H3 提示词、真实 H3 视频调用、视频质检和人工正式选片、剪辑/字幕/音轨与成片导出。不能把预制作计划当成可播放视频，也不得为了提供一个看似可点击的页面而放宽 Replica-only API。

## 输入与复用

- 复用当前 `SOURCE_TEXT` 不可变上传、版本失效与 Artifact Graph。
- 复用 `script-analysis` 专业技能手册及其 typed 输出。
- 复用 `script_localization.long_text` 的 **纯确定性无损分块与来源指纹算法**和文本 Provider/Task/ProviderJob 技术适配，不复用剧本本土化的服务和项目类型授权。
- 新增独立 `script-world-design`、`script-storyboard-directing` 专业技能手册和 `SCRIPT_TO_DRAMA_PREPRODUCTION` 调度器、修订表、API 与 UI。

## 规则

原文是 Source Fact；视觉形态补足需标成 Visual Inference，影响剧情的歧义进入人工决策。按自然场次/段落分块，跨段承接使用同一人物/场景/道具 registry；所有分段完成且通过引用校验后原子发布正式产物。模型上下文、JSON schema、输出长度和分段遗漏失败时保留检查点，拒绝发布不完整下游。修改原剧本会使此项目下游版本自动过期，不影响其他项目。

## 依据

Final Draft 剧本元素：https://kb.finaldraft.com/hc/en-us/articles/27646947570196-What-are-script-elements

StudioBinder 剧本拆解：https://www.studiobinder.com/tutorials/breakdown/intro-to-script-breakdowns/

Adobe 分镜/镜头清单：https://www.adobe.com/uk/creativecloud/video/discover/shot-list.html

Adobe 镜头连续性：https://www.adobe.com/creativecloud/video/production/cinematography/camera-shots-and-angles/sequence-shot.html

Runway 视频提示编排：https://help.runwayml.com/hc/en-us/articles/48324313115155-Image-to-Video-Prompting-Guide

## 验收

预制作工程验收不等于全项目完成。只有实际资产图片、模型专属提示词、真实视频 Provider/QC/正式选片和合成成片均由独立合规合同贯通、经同一真实项目人工验收后，才能将剧本生成短剧项目标记为可完整使用。