import pytest

from app.core.errors import AppError
from app.projects.enums import SourceUnderstandingProvider
from app.target_assets.providers import (
    P13_REVIEW_LANGUAGE,
    P13_REVIEW_LANGUAGE_CONTRACT,
    TargetAssetsProviderInput,
    _assert_review_language,
    _profile,
    _prompt,
    _target_bible_visual_view,
)
from app.target_assets.schemas import (
    P13_PROMPT_VERSION,
    P13_TARGET_ASSET_CONTRACT,
    ProviderCharacterAssetSemantic,
    ProviderPropAssetSemantic,
    ProviderSceneAssetSemantic,
    TargetAssetsSemantic,
)


def _chinese_review_semantic() -> TargetAssetsSemantic:
    return TargetAssetsSemantic(
        characters=[
            ProviderCharacterAssetSemantic(
                target_character_id="tchr_lila",
                demographic_direction="29 岁的华裔美国市场营销从业者 Lila Xu，整体呈现自然、干练的都市职业女性气质。",
                face_direction="东亚女性柔和椭圆脸，浅棕色杏仁眼，自然眉形与轻薄日常妆感，表情从克制不满逐步转为坚定。",
                hair_direction="深栗色中长直发，中分并保持自然垂落，不做夸张卷发或高饱和挑染。",
                body_direction="身形纤细、站姿自然挺直，动作克制稳定，做出决定后体态更明确有力量感。",
                wardrobe_baseline="基础服装保持简洁、利落的都市休闲风格，以白色、浅灰和低饱和中性色为主，剪裁干净，饰品克制；具体 Scene/Shot variation 留给后续生产阶段。",
                signature_visual_features=["深栗色中分直发", "自然轻妆", "小号珍珠耳钉", "克制而稳定的表情变化"],
                continuity_constraints=["Lila Xu 的脸型、发际线、身材比例和主发型跨镜保持一致。"],
                generation_guidance=["保持真实皮肤纹理与稳定面部几何；未来执行时可保留 iPhone 等目标地区实体写法。"],
                negative_constraints=["避免浓重舞台妆", "避免突然改变年龄感", "避免夸张歇斯底里的表演姿态"],
            )
        ],
        scenes=[
            ProviderSceneAssetSemantic(
                target_scene_id="tscn_austin_hallway",
                layout="Austin 中层公寓五楼为狭长直线走廊，502 与 503 房门相邻，电梯位于一端，安全出口位于另一端。",
                architecture_style="美国中层出租公寓常见的实用型公共区域建筑风格，结构简洁，不做酒店化豪华装修。",
                interior_exterior_style="室内公共走廊以浅米色墙面、深色金属门和不锈钢电梯为主，保持普通住宅公共空间质感。",
                materials_palette=["浅米色乳胶漆墙面", "深棕色金属房门", "不锈钢电梯门", "浅灰色耐磨地材"],
                fixed_landmarks=["502 门牌", "503 门牌", "不锈钢电梯", "绿色 EXIT 标识", "墙面消防报警装置"],
                lighting_baseline="使用略偏冷的顶部公共照明，整体均匀，阴影柔和，不制造电影棚式强轮廓光。",
                time_of_day_baseline="公共走廊视觉身份主要由顶部人工照明决定；具体 Shot 的昼夜变化由后续 Storyboard / Shot context 决定。",
                continuity_constraints=["502、503、电梯和 EXIT 标识的相对位置跨镜保持固定。"],
                generation_guidance=["保持走廊消失点、门距和电梯位置稳定，目标地区专名 Austin 可保留英文。"],
                negative_constraints=["避免改成豪华酒店走廊", "避免改变门牌和电梯拓扑", "避免随机增加大型装饰物"],
            )
        ],
        props=[
            ProviderPropAssetSemantic(
                target_prop_id="tprop_blue_roses",
                visual_form="12 枝鲜艳蓝玫瑰搭配少量尤加利叶，使用透明玻璃花瓶或配送包装呈现，整体保持普通鲜花配送商品的真实感。",
                materials=["新鲜玫瑰花瓣与花茎", "尤加利叶", "透明玻璃", "花艺包装纸"],
                color_palette=["高饱和真蓝色花瓣", "灰绿色尤加利叶", "透明玻璃", "中性灰包装"],
                scale_reference="整体约前臂长度，一名成年人可以单手轻松拿取；零售价 $19.99 的体量感不能被放大成婚礼捧花。",
                signature_visual_features=["蓝色玫瑰", "12 枝左右的花量", "紧凑轮廓", "$19.99 的普通配送花束定位"],
                continuity_constraints=["花束体量、蓝色色相、包装轮廓和主要花量跨镜保持稳定。"],
                generation_guidance=["表现真实花瓣纹理和自然新鲜度；金额 $19.99 保留美国目标地区写法。"],
                negative_constraints=["避免变成红玫瑰", "避免超大婚礼捧花", "避免随机改变包装主色"],
            )
        ],
    )


def _english_review_semantic() -> TargetAssetsSemantic:
    semantic = _chinese_review_semantic().model_copy(deep=True)
    character = semantic.characters[0]
    character.demographic_direction = "29-year-old Chinese-American marketing specialist with a grounded contemporary professional presentation."
    character.face_direction = "Soft oval East Asian face, warm brown almond eyes, natural brows and minimal everyday makeup."
    character.hair_direction = "Long straight dark chestnut hair with a simple center part and no bold highlights."
    character.body_direction = "Slender average-height build with controlled upright posture and subtle gestures."
    character.wardrobe_baseline = "White cold-shoulder top, wide-leg trousers, neutral home loungewear and minimal jewelry."
    character.signature_visual_features = ["dark chestnut hair", "natural makeup", "pearl studs"]
    character.continuity_constraints = ["Keep facial proportions and hairstyle stable across shots."]
    character.generation_guidance = ["Maintain realistic skin texture and stable facial geometry."]
    character.negative_constraints = ["No age drift", "No hairstyle swaps", "No dramatic makeup"]
    return semantic


def test_p13_v3_prompt_separates_chinese_review_language_and_enforces_asset_local_scope() -> None:
    assert P13_PROMPT_VERSION == "p13-replica-target-assets-v3"
    assert P13_TARGET_ASSET_CONTRACT == "replica-target-visual-identity-v2"
    assert P13_REVIEW_LANGUAGE == "zh-CN"
    assert P13_REVIEW_LANGUAGE_CONTRACT == "zh-cn-human-review-asset-local-visual-v2"

    prompt = _prompt(
        TargetAssetsProviderInput(
            target_language="en-US",
            target_region="US",
            target_bible={"visual_style": "grounded US vertical drama"},
            entity_manifest={"characters": [], "scenes": [], "props": []},
        )
    )
    assert "review_language: zh-CN" in prompt
    assert "target_language 是未来目标受众成品语言，不是本次审核说明语言" in prompt
    assert "不得因为 target_language=en-US 就把本次审核正文整体输出为英文" in prompt
    assert "Lila Xu" in prompt and "HEB" in prompt and "$19.99" in prompt
    assert "Generation Adapter" in prompt
    assert "只能描述当前人物、场景或道具的视觉身份稳定性" in prompt
    assert "Story Beat、镜头顺序、对白、节奏、Cliffhanger" in prompt
    assert "wardrobe_baseline 是人物基础视觉身份，不是逐 Scene / 逐 Shot 换装计划" in prompt
    assert "time_of_day_baseline 是场景视觉基线，不是剧情时间轴" in prompt
    assert "不得根据 Scene 顺序、闪回或情绪自行推断" in prompt
    assert "P13 不负责复述 preservation locks" in prompt


def test_p13_visual_projection_omits_global_story_and_dialogue_text_from_provider_prompt() -> None:
    target_bible = {
        "schema_version": "1.0",
        "target_language": "en-US",
        "target_region": "US",
        "target_world": {"setting_summary": "Austin apartment community"},
        "visual_style": "grounded US vertical drama",
        "continuity_rules": ["GLOBAL_STORY_LOCK_SENTINEL"],
        "dialogue_style_rules": ["GLOBAL_DIALOGUE_LOCK_SENTINEL"],
        "adaptation_summary": "GLOBAL_ADAPTATION_SUMMARY_SENTINEL",
        "characters": [
            {
                "target_character_id": "tchr_lila",
                "source_character_id": "src_lila",
                "display_name": "Lila Xu",
                "localized_identity": "Austin marketing professional",
                "appearance_direction": "Grounded contemporary urban styling",
                "personality_constraints": ["PERSONALITY_SENTINEL"],
                "continuity_rules": ["ENTITY_VISUAL_GUARDRAIL_SENTINEL"],
            }
        ],
        "scenes": [],
        "props": [],
    }

    visual_view = _target_bible_visual_view(target_bible)
    assert "continuity_rules" not in visual_view
    assert "dialogue_style_rules" not in visual_view
    assert "adaptation_summary" not in visual_view
    assert "source_character_id" not in visual_view["characters"][0]
    assert "personality_constraints" not in visual_view["characters"][0]
    assert visual_view["characters"][0]["continuity_rules"] == ["ENTITY_VISUAL_GUARDRAIL_SENTINEL"]

    prompt = _prompt(
        TargetAssetsProviderInput(
            target_language="en-US",
            target_region="US",
            target_bible=target_bible,
            entity_manifest={
                "characters": [{"target_character_id": "tchr_lila", "display_name": "Lila Xu"}],
                "scenes": [],
                "props": [],
            },
        )
    )
    assert "GLOBAL_STORY_LOCK_SENTINEL" not in prompt
    assert "GLOBAL_DIALOGUE_LOCK_SENTINEL" not in prompt
    assert "GLOBAL_ADAPTATION_SUMMARY_SENTINEL" not in prompt
    assert "PERSONALITY_SENTINEL" not in prompt
    assert "ENTITY_VISUAL_GUARDRAIL_SENTINEL" in prompt


def test_p13_review_language_accepts_chinese_explanations_with_target_region_proper_nouns() -> None:
    _assert_review_language(_chinese_review_semantic())


def test_p13_review_language_rejects_english_dominant_provider_packet() -> None:
    with pytest.raises(AppError) as captured:
        _assert_review_language(_english_review_semantic())
    assert captured.value.code == "P13_PROVIDER_REVIEW_LANGUAGE_INVALID"
    assert captured.value.details["review_language"] == "zh-CN"
    assert captured.value.details["invalid_entities"][0]["asset_type"] == "CHARACTER"


def test_p13_provider_profile_versions_chinese_asset_local_review_behavior() -> None:
    profile = _profile(
        SourceUnderstandingProvider.DOUBAO_SEED_2_1_PRO_API,
        "volcengine-ark",
        "test-model",
        "CLOUD_API_TEXT_ONLY",
    )
    assert profile["prompt_version"] == "p13-replica-target-assets-v3"
    assert profile["target_asset_contract"] == "replica-target-visual-identity-v2"
    assert profile["review_language"] == "zh-CN"
    assert profile["review_language_contract"] == P13_REVIEW_LANGUAGE_CONTRACT
