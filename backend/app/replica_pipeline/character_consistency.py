from dataclasses import dataclass

from PIL import Image


@dataclass(frozen=True)
class CharacterConsistencyResult:
    passed: bool
    checks: dict[str, str]
    reason: str | None = None


def validate_character_asset_identity(image_path: str) -> CharacterConsistencyResult:
    """人物资产生成后的基础质量门禁。

    当前阶段提供确定性图片校验；后续在此基础上接入
    face embedding / CLIP / InsightFace 相似度模型。
    """
    try:
        with Image.open(image_path) as image:
            width, height = image.size
            image.verify()
    except Exception as exc:
        return CharacterConsistencyResult(False, {"image_decode": "FAIL"}, f"image_invalid:{exc}")

    if width <= 0 or height <= 0:
        return CharacterConsistencyResult(False, {"size": "FAIL"}, "invalid_dimensions")

    return CharacterConsistencyResult(
        True,
        {
            "image_decode": "PASS",
            "size": "PASS",
        },
    )


def validate_character_reference_set(reference_paths: dict[str, str]) -> CharacterConsistencyResult:
    """角色多视图一致性检查入口。

    当前阶段先完成统一门禁接口和确定性图片校验；
    face embedding / CLIP / InsightFace 相似度模型将在此处接入。
    """
    # New character boards persist explicit orientation roles.  Keep accepting
    # legacy names so historical candidates remain inspectable, but treat the
    # deterministic FULL_BODY_FRONT crop as the current front identity anchor.
    front_path = (
        reference_paths.get("FULL_BODY_FRONT")
        or reference_paths.get("FULL_BODY")
        or reference_paths.get("front")
    )
    face_path = reference_paths.get("FACE") or reference_paths.get("face")
    missing = [
        name
        for name, path in (("front", front_path), ("face", face_path))
        if not path
    ]
    if missing:
        return CharacterConsistencyResult(
            False,
            {"reference_set": "FAIL"},
            f"missing_reference_views:{','.join(missing)}",
        )

    checks = {"reference_set": "PASS"}
    for view, path in reference_paths.items():
        result = validate_character_asset_identity(path)
        checks[f"{view}_image"] = "PASS" if result.passed else "FAIL"
        if not result.passed:
            return CharacterConsistencyResult(False, checks, result.reason)

    checks.update({
        "face_similarity": "PENDING",
        "hair_similarity": "PENDING",
        "wardrobe_similarity": "PENDING",
    })
    return CharacterConsistencyResult(True, checks)
