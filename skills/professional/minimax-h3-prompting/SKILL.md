# MiniMax H3 Multi-reference AV Prompting

## Role

This is the model-specific prompt skill for MiniMax H3. It converts stable product artifacts into H3-native execution instructions. It is not a generic prompt template and it does not execute the model.

## Inputs

- CURRENT TARGET_STORYBOARD v2
- CURRENT TARGET_ASSETS v2 with real approved images

## Reference contract

H3 Ref2VA can consume ordered image references. The skill assigns deterministic slots `1..9`; the prompt must reference them with the exact tags `<Picture 1>`, `<Picture 2>`, ... in the same order used by the Runtime graph.

Priority per shot: scene identity first, speaking/visible characters second, remaining visible characters third, important props last. Deduplicate by reference media. Missing required identity media fails closed.

## Prompt structure

Each segment contains:

1. reference identity statements using `<Picture N>`;
2. Chinese localized visual intent translated into clear model execution instructions without changing story facts;
3. source-preserved camera framing/movement and action timing;
4. exact target-language dialogue to be spoken verbatim once;
5. native synchronized stereo audio, lip movement, ambience and motivated SFX;
6. continuity and negative constraints;
7. output ratio and bounded duration.

`target_dialogue_zh` is for the Chinese operator UI only and must never be included as additional spoken text.

## Separation

The Prompt Skill owns prompt/reference compilation. ComfyUI/SGLang/cloud adapters only execute the compiled segment and may not rewrite, enrich or substitute identities.
