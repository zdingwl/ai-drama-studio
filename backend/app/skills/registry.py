from pathlib import Path

from app.projects.enums import ProjectType
from app.skills.models import ArtifactType, Capability, RootSkillDefinition, RootSkillDetail, SkillStepDefinition


_MANUAL_ROOT = Path(__file__).parent / "manuals"


def _step(
    step_id: str,
    phase: str,
    title: str,
    description: str,
    capabilities: tuple[Capability, ...],
    requires: tuple[ArtifactType, ...] = (),
    produces: tuple[ArtifactType, ...] = (),
) -> SkillStepDefinition:
    return SkillStepDefinition(
        id=step_id,
        phase=phase,
        title=title,
        description=description,
        capabilities=capabilities,
        requires=requires,
        produces=produces,
    )


ROOT_SKILLS: dict[ProjectType, RootSkillDefinition] = {
    ProjectType.REPLICA: RootSkillDefinition(
        id="project.replica",
        project_type=ProjectType.REPLICA,
        title="复刻短剧",
        purpose="保留原剧故事与节奏，把人物、场景、文化和对白替换成目标地区版本并重新生成。",
        manual_path="manuals/replica/SKILL.md",
        steps=(
            _step("source_input", "输入", "导入原片", "登记原始短剧 Episode。", (Capability.SOURCE_VIDEO_INGEST,), produces=(ArtifactType.SOURCE_VIDEO,)),
            _step("source_evidence", "理解", "建立原片证据", "完成媒体检查、镜头时间锚点和原对白证据。", (Capability.MEDIA_PREFLIGHT, Capability.SHOT_BOUNDARY, Capability.SOURCE_DIALOGUE_EVIDENCE), requires=(ArtifactType.SOURCE_VIDEO,), produces=(ArtifactType.SHOT_ANCHORS, ArtifactType.SOURCE_DIALOGUE)),
            _step("source_story", "理解", "整集故事与节奏", "先理解整集，再提取故事骨架和节奏骨架。", (Capability.EPISODE_UNDERSTANDING, Capability.STORY_RHYTHM), requires=(ArtifactType.SOURCE_VIDEO, ArtifactType.SHOT_ANCHORS, ArtifactType.SOURCE_DIALOGUE), produces=(ArtifactType.SOURCE_BIBLE, ArtifactType.STORY_SKELETON, ArtifactType.RHYTHM_SKELETON)),
            _step("source_breakdown", "理解", "逐镜拉片与归一", "带整集知识做逐镜拉片，并归一人物、场景和关键道具。", (Capability.SHOT_BREAKDOWN, Capability.IDENTITY_RESOLUTION, Capability.SCENE_RESOLUTION, Capability.PROP_RESOLUTION), requires=(ArtifactType.SOURCE_BIBLE, ArtifactType.SHOT_ANCHORS), produces=(ArtifactType.SOURCE_SHOT_FACTS, ArtifactType.SOURCE_CHARACTERS, ArtifactType.SOURCE_SCENES, ArtifactType.SOURCE_PROPS)),
            _step("source_finalize", "理解", "原片分析定稿", "把可追溯的原片事实冻结为下游唯一正式来源。", (Capability.SOURCE_SNAPSHOT,), requires=(ArtifactType.SOURCE_BIBLE, ArtifactType.SOURCE_SHOT_FACTS, ArtifactType.SOURCE_CHARACTERS, ArtifactType.SOURCE_SCENES, ArtifactType.SOURCE_PROPS), produces=(ArtifactType.SOURCE_VIDEO_SNAPSHOT,)),
            _step("target_localize", "目标版本", "本土化替换", "锁定故事和节奏，建立目标地区人物、场景、道具与剧本。", (Capability.LOCALIZATION, Capability.TARGET_BIBLE, Capability.TARGET_SCRIPT), requires=(ArtifactType.SOURCE_VIDEO_SNAPSHOT, ArtifactType.STORY_SKELETON, ArtifactType.RHYTHM_SKELETON), produces=(ArtifactType.ADAPTATION_PLAN, ArtifactType.TARGET_BIBLE, ArtifactType.TARGET_SCRIPT)),
            _step("target_assets", "目标版本", "目标资产", "形成可复用的人物、场景和关键道具资产。", (Capability.TARGET_ASSETS,), requires=(ArtifactType.TARGET_BIBLE,), produces=(ArtifactType.TARGET_ASSETS,)),
            _step("voice_timing", "分镜", "目标对白与时长", "先生成目标配音，再根据真实语音时长做最小必要的节奏适配。", (Capability.TTS, Capability.TIMING), requires=(ArtifactType.TARGET_SCRIPT,), produces=(ArtifactType.TARGET_AUDIO, ArtifactType.TIMING_PLAN)),
            _step("replica_storyboard", "分镜", "复刻分镜", "把原镜头关系与目标资产组合成可编辑复刻分镜。", (Capability.STORYBOARD,), requires=(ArtifactType.SOURCE_VIDEO_SNAPSHOT, ArtifactType.TARGET_ASSETS, ArtifactType.TIMING_PLAN), produces=(ArtifactType.TARGET_STORYBOARD, ArtifactType.GENERATION_SEGMENTS)),
            _step("generate", "生成", "视频生成与质检", "生成目标镜头，有限重试并选择正式可用结果。", (Capability.VIDEO_GENERATION, Capability.QC_SELECTION), requires=(ArtifactType.GENERATION_SEGMENTS,), produces=(ArtifactType.GENERATED_VIDEO, ArtifactType.GENERATION_SELECTION)),
            _step("post", "成片", "口型与后期", "完成口型、音频、字幕、剪辑和成片输出。", (Capability.LIP_SYNC, Capability.POST_PRODUCTION), requires=(ArtifactType.GENERATION_SELECTION, ArtifactType.TARGET_AUDIO), produces=(ArtifactType.FINAL_OUTPUT,)),
        ),
    ),
    ProjectType.REDRAW: RootSkillDefinition(
        id="project.redraw",
        project_type=ProjectType.REDRAW,
        title="重绘短剧",
        purpose="尽量保留原剧情、剪辑与表演结构，重点重新设计并生成视觉。",
        manual_path="manuals/redraw/SKILL.md",
        steps=(
            _step("source_input", "输入", "导入原片", "登记需要重绘的 Episode。", (Capability.SOURCE_VIDEO_INGEST,), produces=(ArtifactType.SOURCE_VIDEO,)),
            _step("source_understand", "理解", "原片结构理解", "建立镜头锚点、对白证据并理解原片人物、场景和镜头结构。", (Capability.MEDIA_PREFLIGHT, Capability.SHOT_BOUNDARY, Capability.SOURCE_DIALOGUE_EVIDENCE, Capability.EPISODE_UNDERSTANDING, Capability.SHOT_BREAKDOWN), requires=(ArtifactType.SOURCE_VIDEO,), produces=(ArtifactType.SHOT_ANCHORS, ArtifactType.SOURCE_DIALOGUE, ArtifactType.SOURCE_BIBLE, ArtifactType.SOURCE_SHOT_FACTS)),
            _step("source_finalize", "理解", "原片分析定稿", "形成可供重绘使用的正式原片事实。", (Capability.SOURCE_SNAPSHOT,), requires=(ArtifactType.SOURCE_BIBLE, ArtifactType.SOURCE_SHOT_FACTS), produces=(ArtifactType.SOURCE_VIDEO_SNAPSHOT,)),
            _step("visual_plan", "目标版本", "视觉重绘方案", "确定目标人物、场景、时代和视觉风格。", (Capability.LOCALIZATION, Capability.TARGET_BIBLE, Capability.TARGET_ASSETS), requires=(ArtifactType.SOURCE_VIDEO_SNAPSHOT,), produces=(ArtifactType.ADAPTATION_PLAN, ArtifactType.TARGET_BIBLE, ArtifactType.TARGET_ASSETS)),
            _step("storyboard", "分镜", "重绘分镜", "保持原剪辑/表演关系，生成目标视觉分镜。", (Capability.STORYBOARD, Capability.TIMING), requires=(ArtifactType.SOURCE_VIDEO_SNAPSHOT, ArtifactType.TARGET_ASSETS), produces=(ArtifactType.TIMING_PLAN, ArtifactType.TARGET_STORYBOARD, ArtifactType.GENERATION_SEGMENTS)),
            _step("generate", "生成", "重绘生成与质检", "逐段重绘并选择正式结果。", (Capability.VIDEO_GENERATION, Capability.QC_SELECTION), requires=(ArtifactType.GENERATION_SEGMENTS,), produces=(ArtifactType.GENERATED_VIDEO, ArtifactType.GENERATION_SELECTION)),
            _step("post", "成片", "音频与后期", "按项目音频策略挂回或重建音频并输出成片。", (Capability.POST_PRODUCTION,), requires=(ArtifactType.GENERATION_SELECTION,), produces=(ArtifactType.FINAL_OUTPUT,)),
        ),
    ),
    ProjectType.TRANSLATION: RootSkillDefinition(
        id="project.translation",
        project_type=ProjectType.TRANSLATION,
        title="翻译短剧",
        purpose="尽量保持原始画面不变，重建目标语言对白、时长、口型和字幕。",
        manual_path="manuals/translation/SKILL.md",
        steps=(
            _step("source_input", "输入", "导入原片", "登记需要翻译的 Episode。", (Capability.SOURCE_VIDEO_INGEST,), produces=(ArtifactType.SOURCE_VIDEO,)),
            _step("dialogue", "理解", "对白与说话信息", "获取带时间证据的原对白与镜头时间锚点。", (Capability.MEDIA_PREFLIGHT, Capability.SHOT_BOUNDARY, Capability.SOURCE_DIALOGUE_EVIDENCE), requires=(ArtifactType.SOURCE_VIDEO,), produces=(ArtifactType.SHOT_ANCHORS, ArtifactType.SOURCE_DIALOGUE)),
            _step("target_dialogue", "目标版本", "翻译与本土化对白", "保留原意图和情绪，生成目标语言正式对白。", (Capability.LOCALIZATION, Capability.TARGET_SCRIPT), requires=(ArtifactType.SOURCE_DIALOGUE,), produces=(ArtifactType.ADAPTATION_PLAN, ArtifactType.TARGET_SCRIPT)),
            _step("voice_timing", "分镜", "配音与时间适配", "以真实 TTS 时长决定压缩对白、延长、裁剪或反应镜头承接。", (Capability.TTS, Capability.TIMING), requires=(ArtifactType.TARGET_SCRIPT, ArtifactType.SHOT_ANCHORS), produces=(ArtifactType.TARGET_AUDIO, ArtifactType.TIMING_PLAN)),
            _step("post", "成片", "口型、字幕与合成", "对需要的可见说话人做口型同步，重建目标语言音轨并输出。", (Capability.LIP_SYNC, Capability.POST_PRODUCTION), requires=(ArtifactType.TARGET_AUDIO, ArtifactType.TIMING_PLAN, ArtifactType.SOURCE_VIDEO), produces=(ArtifactType.FINAL_OUTPUT,)),
        ),
    ),
    ProjectType.NOVEL_TO_DRAMA: RootSkillDefinition(
        id="project.novel_to_drama",
        project_type=ProjectType.NOVEL_TO_DRAMA,
        title="小说生成短剧",
        purpose="把小说转换成短剧化剧本、世界、分镜并生成成片。",
        manual_path="manuals/novel_to_drama/SKILL.md",
        steps=(
            _step("source_input", "输入", "导入小说", "登记小说或故事文本。", (Capability.SOURCE_TEXT_INGEST,), produces=(ArtifactType.SOURCE_TEXT,)),
            _step("novel_adapt", "理解", "小说短剧化", "理解人物和故事，提炼 Hook、冲突、反转并规划 Episode。", (Capability.SCRIPT_ANALYSIS, Capability.STORY_RHYTHM, Capability.NOVEL_ADAPTATION), requires=(ArtifactType.SOURCE_TEXT,), produces=(ArtifactType.SOURCE_TEXT_SNAPSHOT, ArtifactType.STORY_SKELETON, ArtifactType.RHYTHM_SKELETON, ArtifactType.ADAPTATION_PLAN)),
            _step("target_script", "目标版本", "正式短剧剧本", "形成可生成的目标剧本和统一目标世界。", (Capability.TARGET_SCRIPT, Capability.TARGET_BIBLE), requires=(ArtifactType.SOURCE_TEXT_SNAPSHOT, ArtifactType.ADAPTATION_PLAN), produces=(ArtifactType.TARGET_SCRIPT, ArtifactType.TARGET_BIBLE)),
            _step("assets_storyboard", "分镜", "资产与导演分镜", "建立人物、场景、道具资产并完成目标分镜。", (Capability.TARGET_ASSETS, Capability.STORYBOARD), requires=(ArtifactType.TARGET_SCRIPT, ArtifactType.TARGET_BIBLE), produces=(ArtifactType.TARGET_ASSETS, ArtifactType.TARGET_STORYBOARD)),
            _step("voice_timing", "分镜", "配音与生成窗口", "生成目标对白音频并形成时间计划和生成片段。", (Capability.TTS, Capability.TIMING), requires=(ArtifactType.TARGET_SCRIPT, ArtifactType.TARGET_STORYBOARD), produces=(ArtifactType.TARGET_AUDIO, ArtifactType.TIMING_PLAN, ArtifactType.GENERATION_SEGMENTS)),
            _step("generate", "生成", "视频生成与质检", "生成镜头、质检并选择正式结果。", (Capability.VIDEO_GENERATION, Capability.QC_SELECTION), requires=(ArtifactType.GENERATION_SEGMENTS,), produces=(ArtifactType.GENERATED_VIDEO, ArtifactType.GENERATION_SELECTION)),
            _step("post", "成片", "口型与后期", "完成目标短剧成片。", (Capability.LIP_SYNC, Capability.POST_PRODUCTION), requires=(ArtifactType.GENERATION_SELECTION, ArtifactType.TARGET_AUDIO), produces=(ArtifactType.FINAL_OUTPUT,)),
        ),
    ),
    ProjectType.SCRIPT_TO_DRAMA: RootSkillDefinition(
        id="project.script_to_drama",
        project_type=ProjectType.SCRIPT_TO_DRAMA,
        title="剧本生成短剧",
        purpose="把已有剧本标准化为可生成的导演方案并生成完整短剧。",
        manual_path="manuals/script_to_drama/SKILL.md",
        steps=(
            _step("source_input", "输入", "导入剧本", "登记用户已有剧本。", (Capability.SOURCE_TEXT_INGEST,), produces=(ArtifactType.SOURCE_TEXT,)),
            _step("script_analyze", "理解", "剧本整理", "标准化场次、人物、对白、动作与故事节奏。", (Capability.SCRIPT_ANALYSIS, Capability.STORY_RHYTHM), requires=(ArtifactType.SOURCE_TEXT,), produces=(ArtifactType.SOURCE_TEXT_SNAPSHOT, ArtifactType.STORY_SKELETON, ArtifactType.RHYTHM_SKELETON)),
            _step("target_world", "目标版本", "目标世界与正式剧本", "在用户允许范围内补足可视化信息，形成目标世界和正式剧本。", (Capability.TARGET_BIBLE, Capability.TARGET_SCRIPT), requires=(ArtifactType.SOURCE_TEXT_SNAPSHOT,), produces=(ArtifactType.TARGET_BIBLE, ArtifactType.TARGET_SCRIPT)),
            _step("assets_storyboard", "分镜", "资产与导演分镜", "建立目标资产并完成导演分镜。", (Capability.TARGET_ASSETS, Capability.STORYBOARD), requires=(ArtifactType.TARGET_BIBLE, ArtifactType.TARGET_SCRIPT), produces=(ArtifactType.TARGET_ASSETS, ArtifactType.TARGET_STORYBOARD)),
            _step("voice_timing", "分镜", "配音与生成窗口", "用真实对白时长形成时间计划和生成片段。", (Capability.TTS, Capability.TIMING), requires=(ArtifactType.TARGET_SCRIPT, ArtifactType.TARGET_STORYBOARD), produces=(ArtifactType.TARGET_AUDIO, ArtifactType.TIMING_PLAN, ArtifactType.GENERATION_SEGMENTS)),
            _step("generate", "生成", "视频生成与质检", "生成镜头、质检并选择正式结果。", (Capability.VIDEO_GENERATION, Capability.QC_SELECTION), requires=(ArtifactType.GENERATION_SEGMENTS,), produces=(ArtifactType.GENERATED_VIDEO, ArtifactType.GENERATION_SELECTION)),
            _step("post", "成片", "口型与后期", "完成音频、口型、字幕、剪辑和成片。", (Capability.LIP_SYNC, Capability.POST_PRODUCTION), requires=(ArtifactType.GENERATION_SELECTION, ArtifactType.TARGET_AUDIO), produces=(ArtifactType.FINAL_OUTPUT,)),
        ),
    ),
    ProjectType.SCRIPT_LOCALIZATION: RootSkillDefinition(
        id="project.script_localization",
        project_type=ProjectType.SCRIPT_LOCALIZATION,
        title="剧本本土化",
        purpose="保留故事骨架，把剧本中的文化、身份、制度、场景、道具与表达改成目标地区成立的版本。",
        manual_path="manuals/script_localization/SKILL.md",
        steps=(
            _step("source_input", "输入", "导入原剧本", "登记待本土化剧本。", (Capability.SOURCE_TEXT_INGEST,), produces=(ArtifactType.SOURCE_TEXT,)),
            _step("script_analyze", "理解", "原剧本理解", "理解故事、人物关系、场景、关键道具和节奏骨架。", (Capability.SCRIPT_ANALYSIS, Capability.STORY_RHYTHM), requires=(ArtifactType.SOURCE_TEXT,), produces=(ArtifactType.SOURCE_TEXT_SNAPSHOT, ArtifactType.STORY_SKELETON, ArtifactType.RHYTHM_SKELETON)),
            _step("localize", "目标版本", "本土化方案", "判断哪些元素必须保留、哪些需要替换，并说明文化理由。", (Capability.LOCALIZATION,), requires=(ArtifactType.SOURCE_TEXT_SNAPSHOT, ArtifactType.STORY_SKELETON), produces=(ArtifactType.ADAPTATION_PLAN,)),
            _step("target_script", "目标版本", "目标地区剧本", "生成目标地区自然成立的正式剧本。", (Capability.TARGET_SCRIPT,), requires=(ArtifactType.ADAPTATION_PLAN,), produces=(ArtifactType.TARGET_SCRIPT,)),
            _step("export", "导出", "导出正式剧本", "导出本土化完成的剧本；可后续转为剧本生成短剧项目。", (Capability.EXPORT_SCRIPT,), requires=(ArtifactType.TARGET_SCRIPT,), produces=(ArtifactType.FINAL_OUTPUT,)),
        ),
    ),
}

_SKILL_BY_ID = {skill.id: skill for skill in ROOT_SKILLS.values()}


def list_root_skills() -> list[RootSkillDefinition]:
    return list(ROOT_SKILLS.values())


def get_root_skill(project_type: ProjectType) -> RootSkillDefinition:
    return ROOT_SKILLS[project_type]


def get_root_skill_by_id(skill_id: str) -> RootSkillDefinition | None:
    return _SKILL_BY_ID.get(skill_id)


def get_skill_detail(skill: RootSkillDefinition) -> RootSkillDetail:
    manual_file = Path(__file__).parent / skill.manual_path
    return RootSkillDetail(**skill.model_dump(), manual=manual_file.read_text(encoding="utf-8"))
