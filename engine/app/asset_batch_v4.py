"""03 资产：批量 Shot Final Binding。

职责：
- 一次修改多个 Shot 的人物 / 场景 / 道具绑定；
- 只修改用户明确选择的维度，其他 Binding 原样保留；
- 整个批量动作只创建一个 MANUAL Asset Revision；
- 与单 Shot Binding 共用同一 Final Asset Source of Truth。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import delete

from engine.app.asset_workspace_v3 import (
    AssetWorkspaceError,
    ShotCharacterBinding,
    ShotPropBinding,
    ShotSceneBinding,
    _manual_revision,
    _serialize_workspace,
    _validate_ids,
    _validate_shot,
)
from engine.app.studio_v2 import get_session, new_id


def batch_set_shot_bindings(
    project_id: str,
    shot_ids: list[str],
    *,
    apply_characters: bool,
    character_ids: list[str],
    apply_scene: bool,
    scene_id: str | None,
    apply_props: bool,
    prop_ids: list[str],
) -> dict[str, Any]:
    """批量修改 Shot Binding，并且只产生一个 Revision。

    输入：Shot IDs + 三类 Binding 的 apply 开关和值。
    输出：最新 Asset Workspace。
    为什么：批量设置“客厅”时不能覆盖每个 Shot 已有的人物/道具，也不能为 20 个 Shot
    连续制造 20 个 Revision。
    """

    clean_shot_ids = list(dict.fromkeys(shot_ids))
    if not clean_shot_ids:
        raise AssetWorkspaceError("至少选择一个 Shot")
    if not (apply_characters or apply_scene or apply_props):
        raise AssetWorkspaceError("没有选择需要批量修改的资产类型")

    with get_session() as session:
        shots = [_validate_shot(session, project_id, shot_id) for shot_id in clean_shot_ids]
        clean_character_ids = _validate_ids(session, project_id, "character", character_ids) if apply_characters else []
        clean_prop_ids = _validate_ids(session, project_id, "prop", prop_ids) if apply_props else []
        if apply_scene and scene_id:
            _validate_ids(session, project_id, "scene", [scene_id])

        for shot in shots:
            if apply_characters:
                session.execute(delete(ShotCharacterBinding).where(
                    ShotCharacterBinding.project_id == project_id,
                    ShotCharacterBinding.shot_id == shot.id,
                ))
                for asset_id in clean_character_ids:
                    session.add(ShotCharacterBinding(
                        id=new_id("SHOTCHAR"),
                        project_id=project_id,
                        shot_id=shot.id,
                        character_id=asset_id,
                        source="MANUAL",
                    ))

            if apply_scene:
                session.execute(delete(ShotSceneBinding).where(
                    ShotSceneBinding.project_id == project_id,
                    ShotSceneBinding.shot_id == shot.id,
                ))
                if scene_id:
                    session.add(ShotSceneBinding(
                        id=new_id("SHOTSCENEFINAL"),
                        project_id=project_id,
                        shot_id=shot.id,
                        scene_id=scene_id,
                        source="MANUAL",
                    ))

            if apply_props:
                session.execute(delete(ShotPropBinding).where(
                    ShotPropBinding.project_id == project_id,
                    ShotPropBinding.shot_id == shot.id,
                ))
                for asset_id in clean_prop_ids:
                    session.add(ShotPropBinding(
                        id=new_id("SHOTPROPFINAL"),
                        project_id=project_id,
                        shot_id=shot.id,
                        prop_id=asset_id,
                        source="MANUAL",
                    ))

        labels: list[str] = []
        if apply_characters:
            labels.append("人物")
        if apply_scene:
            labels.append("场景")
        if apply_props:
            labels.append("道具")
        _manual_revision(
            session,
            project_id,
            f"批量修改 {len(shots)} 个 Shot 的{' / '.join(labels)}绑定",
        )
        session.commit()
        return _serialize_workspace(session, project_id)
