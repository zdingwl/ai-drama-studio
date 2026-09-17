# Character Visual Design Professional Skill

## Role

This Skill is responsible for converting a target character semantic identity into a stable visual design specification before image model prompting.

It does not generate images. It does not replace the image model Prompt Skill. It creates the character visual design layer consumed by image generation.

Pipeline:

```text
TARGET_BIBLE Character
        ↓
character-visual-design@1.0.0
        ↓
character visual identity specification
        ↓
model-specific image prompt skill
        ↓
image runtime
        ↓
character reference asset
```

## Hard input

Required:

```text
CURRENT TARGET_BIBLE
```

Optional evidence:

```text
localized storyboard character appearances
canonical target character descriptions
```

The Skill must preserve Target Bible identity. It may enrich visual implementation details but cannot invent a new character identity.

## Design procedure

1. Identity extraction

Extract stable character identity:

- age appearance direction;
- gender presentation when defined;
- facial structure;
- hairstyle;
- body proportion;
- skin tone and visible traits;
- wardrobe baseline;
- signature recognizable features.

2. Visual language design

Define production-ready visual direction:

- cinematic style;
- realism level;
- material description;
- color language;
- silhouette;
- character recognition anchors.

3. Generation constraint design

Produce:

- positive visual guidance;
- identity preservation constraints;
- negative constraints.

4. Prompt handoff

The output is passed to the selected image model Professional Prompt Skill.

## Character consistency rules

The generated design must prioritize:

```text
face identity
→ hairstyle
→ body silhouette
→ wardrobe topology
→ signature details
```

Do not describe temporary scene actions as character identity.

Do not add:

- scene background;
- camera shot story content;
- dialogue behavior;
- unrelated props;
- temporary emotions as permanent appearance.

## Output contract

CharacterVisualDesignPacket:

```text
character_id
identity_summary
face_design
hair_design
body_design
wardrobe_design
style_direction
signature_features[]
positive_guidance[]
negative_constraints[]
continuity_rules[]
```

## Separation

This Skill owns:

```text
character visual design
```

Image model Prompt Skills own:

```text
model-specific prompt syntax
reference image strategy
runtime parameters
```

Runtime owns:

```text
actual image generation
media persistence
asset binding
```
