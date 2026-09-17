# Character Visual Design Professional Skill

## Role

This Skill is responsible for converting a target character semantic identity into a stable visual design specification before image model prompting.

It does not generate images. It does not replace the image model Prompt Skill. It creates the character visual design layer consumed by image generation.

Pipeline:

```text
CURRENT TARGET_STORYBOARD Character
        + optional CURRENT TARGET_BIBLE identity constraints
        ↓
character-visual-design@1.1.0
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
CURRENT TARGET_STORYBOARD
```

Optional evidence:

```text
CURRENT TARGET_BIBLE
```

The five-step production chain must not be blocked by the historical P11 Target Bible. The localized storyboard is the required semantic source. When a CURRENT TARGET_BIBLE exists, matching target character identity/appearance/continuity fields are additional stable constraints and must not be contradicted.

The Skill may convert existing appearance evidence into concrete production-ready visual implementation details, but it cannot invent a new character identity, relationship, occupation, ethnicity, scar, tattoo, accessory, or signature prop that is not supported upstream.

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
