# MiniMax H3 Multi-reference AV Prompting

## Role

This is the model-specific prompt skill for MiniMax H3. It converts stable product artifacts into H3-native execution instructions. It is not a generic prompt template and it does not execute the model.

## Inputs

- CURRENT TARGET_STORYBOARD v2
- CURRENT TARGET_ASSETS v2 with real approved images

## Reference contract

H3 Ref2VA can consume ordered image references. The skill assigns deterministic slots `1..9`; the prompt must reference them with the exact tags `<Picture 1>`, `<Picture 2>`, ... in the same order used by the Runtime graph.

Priority per shot is identity-first: every character in `target_character_ids` receives two canonical references before anything else — `FACE`, then front `FULL_BODY`. These two pictures are the same exact person and must be bound together in the execution prompt. Scene `LAYOUT` and important prop `DETAIL` references use only the remaining slots. Dialogue speakers that are off-screen/voice-over are not visual reference inputs merely because they have a line. Deduplicate by reference media. Missing FACE or front FULL_BODY for a visually present character fails closed; never fall back to the four-panel review board as the H3 identity input.

## Prompt structure

Each segment contains:

1. reference identity statements using `<Picture N>`;
   - for every visible character, explicitly state that its FACE picture and front FULL_BODY picture are the same exact person;
   - lock facial geometry, apparent age, hair, skin tone, body proportions and wardrobe identity across all frames; pose, expression and camera angle may change, identity may not;
   - forbid face morphing, age/hair/body drift, character swapping and cross-character feature mixing;
2. Chinese localized visual intent translated into clear model execution instructions without changing story facts;
3. source-preserved camera framing/movement and action timing;
4. exact target-language dialogue to be spoken verbatim once;
5. native synchronized stereo audio, lip movement, ambience and motivated SFX;
6. continuity and negative constraints;
7. output ratio and bounded duration.

`target_dialogue_zh` is for the Chinese operator UI only and must never be included as additional spoken text.

## Separation

The Prompt Skill owns prompt/reference compilation. ComfyUI/SGLang/cloud adapters only execute the compiled segment and may not rewrite, enrich or substitute identities.
