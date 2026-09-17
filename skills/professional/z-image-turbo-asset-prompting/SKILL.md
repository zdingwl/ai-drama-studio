# Z-Image Turbo Asset Prompting

## Role

This is the image-model-specific Professional Skill for the Replica asset stage. It converts one extracted target asset plus the localized storyboard evidence that actually uses that asset into a Z-Image Turbo execution prompt. It does not generate images and it does not change storyboard semantics.

The upstream `asset-image-generation` Skill owns entity extraction and review/publication. This Skill owns only the model-specific prompt compilation between extraction and the ComfyUI Runtime.

## Hard input

- one Character / Scene / Prop extracted from CURRENT `TARGET_STORYBOARD v2`;
- the Chinese review definition already present on that target entity;
- the localized visual descriptions of shots that actually reference the entity;
- the project visual style.

Do not treat the whole character biography, relationships, marriage, personality prose or dialogue as literal drawable content. Convert only visually observable evidence into the execution prompt. Narrative relationships must never create extra people in an asset image.

## Z-Image Turbo runtime profile

Current Windows production profile:

```text
UNET = z_image_turbo_bf16.safetensors
CLIP = qwen_3_4b.safetensors, type=lumina2
VAE  = ae.safetensors
steps = 8
sampler = res_multistep
scheduler = simple
ModelSamplingAuraFlow shift = 3.0
```

The execution prompt should be concise, concrete English optimized for the image model. Chinese is retained separately in review-facing fields.

## Character asset contract

The Skill must compile a **single-character identity prompt**, not a multi-panel layout prompt. `image_prompt` describes only stable visible identity: facial structure, age appearance, hair, skin, body proportions, baseline wardrobe silhouette/material/color and signature visible features. It must not ask Z-Image Turbo to draw a turnaround/reference/contact sheet or to place front/side/back/face views in one generation. It also must not repeat those Runtime-owned layout words as negative wording in either `image_prompt` or `negative_prompt`: Z-Image Turbo can still react to a negated `reference sheet` / `turnaround` / `multi-panel` phrase and produce miniature duplicated figures.

The Runtime owns the production layout deterministically. Z-Image is responsible for the canonical front identity only:

1. render exactly one **front full-body** master image from this Skill-authored identity prompt;
2. treat that exact front image as the canonical visual identity;
3. pass the canonical front as `Image 1` to `qwen-image-edit-character-asset-prompting@1.0.0` + Qwen Image Edit 2511 for the side-profile derivative;
4. pass the same canonical front to the Qwen edit path for the rear derivative;
5. derive the **face close-up** from the generated front master so the face is literally the same front identity;
6. compose those four panels into one landscape production reference sheet in fixed order.

The front render is the only free text-to-image identity sample. Side/back must never be independent Z-Image text-to-image generations and must never rely on same-seed resemblance. They are reference-image edits governed by the Qwen-specific Professional Skill. Runtime phrases the front as one ordinary full-length studio photograph containing exactly one human figure, without using `character reference`, plural `views`, `turnaround`, `collage`, `contact sheet` or similar layout-trigger words. For compatibility with older authored prompts, Runtime may deterministically remove only Runtime-owned layout clauses before front execution; it must preserve the stable visual identity content.

Do not generate a single mood portrait, action scene, couple image or lifestyle scene. Narrative relationships and temporary story props must not enter the stable character identity prompt.

## Scene asset contract

Generate a clean environment identity reference image. Show the stable spatial layout, architecture/interior direction, materials, fixed landmarks, lighting identity and color palette derived from the localized storyboard. Do not add characters just because characters appear in the scene's story shots. The purpose is reusable scene identity, not reenacting a shot.

## Prop asset contract

Generate an isolated prop identity reference on a clean neutral background. Clearly show form, scale, material, color and signature details. Do not add hands or people unless they are indispensable to understanding scale; prefer a clean product/concept reference.

## Positive and negative separation

Z-Image Turbo's current local workflow uses zeroed negative conditioning, but this must not be worked around by pasting a negative list into `image_prompt`. The positive prompt stays affirmative and describes only the desired visible result. Isolation is expressed as positive composition, for example one subject, empty hands, a clean seamless studio background and a typography-free image. `image_prompt` must not contain `Do not`, `Avoid`, `Hard exclusions` or a copied negative list.

`negative_prompt` remains a separate typed field for audit and future adapters. The current Z-Image Runtime does not inject it into the positive encoder. Character layout vocabulary remains Runtime-owned and must not appear in either prompt field.

Character identity is not complete unless the positive prompt contains concrete, evidence-backed detail for facial structure, apparent-age markers, hairstyle/hair color, skin tone, body proportions, wardrobe silhouette, garment material/colors and at least one stable recognition anchor. Generic wording such as “natural facial features” or “average build” cannot replace those details. When evidence is genuinely absent, describe only supported visible traits rather than inventing biography or identity facts.

## Separation

- Prompt Skill: analyzes storyboard evidence and authors final image-model prompt.
- ComfyUI Runtime: executes the compiled stable identity plus deterministic single-person orientation constraints and persists the resulting media.
- Runtime must not infer relationships, invent another person, rewrite the asset identity or replace the prompt with a generic template. Its only compatibility normalization is stripping legacy Runtime-owned layout clauses before character execution.

