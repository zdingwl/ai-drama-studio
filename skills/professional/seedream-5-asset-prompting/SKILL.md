# Seedream 5.0 Asset Prompting

## Role

This Professional Skill compiles one extracted Replica asset into a Seedream 5.0 execution prompt. It does not generate images or alter storyboard semantics.

## Model routing

- Character: Doubao Seedream 5.0 Pro. Generate one authoritative front identity, then use that exact image as the reference for side and rear orientation generations.
- Scene and prop: Doubao Seedream 5.0 Lite.

The Runtime owns reference-image transport, orientation instructions, deterministic sheet composition, persistence, and ProviderJob tracking. The Prompt Skill owns only stable visual identity content.

## Character contract

Describe exactly one person's evidence-backed face, apparent age, hair, skin, body proportions, baseline wardrobe, materials, colors, and stable recognition anchors. Do not include relationships, dialogue, temporary actions, or incidental props. Do not request a multi-panel image, contact sheet, collage, turnaround, or front/side/back layout. Side and rear views must derive from the authoritative front image instead of independent text-to-image sampling.

## Scene contract

Describe the reusable environment identity: spatial layout, architecture, materials, fixed landmarks, lighting baseline, and palette. Do not reenact a story shot or add characters merely because they appear in the storyboard.

## Prop contract

Describe an isolated object with clear form, scale, material, color, and signature details on a clean neutral background. Do not add unrelated hands, people, or scenery.

## Output separation

`image_prompt` is affirmative, concrete English execution text. `negative_prompt` remains a separate typed exclusion field. `review_prompt_zh` is concise Simplified Chinese for the operator. Never emit Artifact ids, media paths, image bytes, or video prompts.
