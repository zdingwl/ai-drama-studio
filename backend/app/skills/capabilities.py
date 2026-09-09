from app.skills.models import Capability, CapabilityAvailability, CapabilityDefinition


CAPABILITIES: tuple[CapabilityDefinition, ...] = (
    CapabilityDefinition(id=Capability.SOURCE_VIDEO_INGEST, title="原片导入", description="接收并登记视频来源素材。", category="input", availability=CapabilityAvailability.AVAILABLE),
    CapabilityDefinition(id=Capability.SOURCE_TEXT_INGEST, title="文本导入", description="接收小说或剧本等文本来源素材。", category="input", availability=CapabilityAvailability.AVAILABLE),
    CapabilityDefinition(id=Capability.MEDIA_PREFLIGHT, title="媒体检查", description="检查视频可解码性、时间基准和基础媒体信息。", category="source", availability=CapabilityAvailability.AVAILABLE),
    CapabilityDefinition(id=Capability.SHOT_BOUNDARY, title="镜头边界", description="建立原片切镜时间锚点，不承担剧情理解。", category="source", availability=CapabilityAvailability.AVAILABLE),
    CapabilityDefinition(id=Capability.SOURCE_DIALOGUE_EVIDENCE, title="对白证据", description="形成带时间证据的原对白与画面文字。", category="source", availability=CapabilityAvailability.AVAILABLE),
    CapabilityDefinition(id=Capability.EPISODE_UNDERSTANDING, title="整集理解", description="理解整集故事、角色关系、场景、关键道具和事件。", category="source", availability=CapabilityAvailability.AVAILABLE),
    CapabilityDefinition(id=Capability.STORY_RHYTHM, title="故事与节奏", description="提取故事骨架、Hook、冲突、反转、爽点和节奏骨架。", category="source", availability=CapabilityAvailability.AVAILABLE),
    CapabilityDefinition(id=Capability.SHOT_BREAKDOWN, title="逐镜拉片", description="在整集上下文中分析动作、表演和镜头语言。", category="source"),
    CapabilityDefinition(id=Capability.IDENTITY_RESOLUTION, title="人物归一", description="使用多证据把不同镜头中的人物归一为稳定角色。", category="source"),
    CapabilityDefinition(id=Capability.SCENE_RESOLUTION, title="场景归一", description="建立稳定场景资产并绑定镜头。", category="source"),
    CapabilityDefinition(id=Capability.PROP_RESOLUTION, title="道具归一", description="识别并归一剧情关键道具。", category="source"),
    CapabilityDefinition(id=Capability.SOURCE_SNAPSHOT, title="原片分析定稿", description="冻结可供下游使用的正式原片事实。", category="source"),
    CapabilityDefinition(id=Capability.SCRIPT_ANALYSIS, title="剧本理解", description="解析剧本结构、角色、场景、对白和事件。", category="text"),
    CapabilityDefinition(id=Capability.NOVEL_ADAPTATION, title="小说短剧化", description="把小说结构改造成短剧化的集、场和冲突结构。", category="text"),
    CapabilityDefinition(id=Capability.LOCALIZATION, title="本土化替换", description="按目标地区替换文化、身份、场景、道具和表达。", category="target"),
    CapabilityDefinition(id=Capability.TARGET_BIBLE, title="目标世界", description="形成统一的目标人物、场景、道具和世界设定。", category="target"),
    CapabilityDefinition(id=Capability.TARGET_SCRIPT, title="目标剧本", description="形成目标语言和目标地区成立的正式剧本。", category="target"),
    CapabilityDefinition(id=Capability.TARGET_ASSETS, title="目标资产", description="生成并管理目标人物、场景和关键道具资产。", category="target"),
    CapabilityDefinition(id=Capability.TTS, title="目标配音", description="生成正式目标对白音频并获得真实语音时长。", category="production"),
    CapabilityDefinition(id=Capability.TIMING, title="时间适配", description="根据真实目标语音时长规划镜头时间，不硬塞对白。", category="production"),
    CapabilityDefinition(id=Capability.STORYBOARD, title="目标分镜", description="形成可编辑的目标导演分镜。", category="production"),
    CapabilityDefinition(id=Capability.VIDEO_GENERATION, title="视频生成", description="把正式生成片段送入视频生成 Provider。", category="generation"),
    CapabilityDefinition(id=Capability.QC_SELECTION, title="生成质检", description="对生成尝试做技术和语义质检并选择正式结果。", category="generation"),
    CapabilityDefinition(id=Capability.LIP_SYNC, title="口型同步", description="根据目标说话人和目标音频执行口型同步。", category="post"),
    CapabilityDefinition(id=Capability.POST_PRODUCTION, title="后期合成", description="完成音轨、字幕、剪辑和成片输出。", category="post"),
    CapabilityDefinition(id=Capability.EXPORT_SCRIPT, title="剧本导出", description="导出本土化或标准化后的正式剧本。", category="output"),
)

CAPABILITY_BY_ID = {item.id: item for item in CAPABILITIES}
