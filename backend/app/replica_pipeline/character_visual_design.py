from dataclasses import dataclass


@dataclass(frozen=True)
class CharacterVisualIdentityPacket:
    character_id: str
    face_identity: str
    hair_identity: str
    body_identity: str
    wardrobe_baseline: str
    signature_features: tuple[str, ...]
    continuity_constraints: tuple[str, ...]


def build_character_visual_identity(character: dict) -> CharacterVisualIdentityPacket:
    return CharacterVisualIdentityPacket(
        character_id=str(character.get('id', '')),
        face_identity=str(character.get('face_identity', '')),
        hair_identity=str(character.get('hair_identity', '')),
        body_identity=str(character.get('body_identity', '')),
        wardrobe_baseline=str(character.get('wardrobe_baseline', '')),
        signature_features=tuple(character.get('signature_features', [])),
        continuity_constraints=tuple(character.get('continuity_constraints', [])),
    )
