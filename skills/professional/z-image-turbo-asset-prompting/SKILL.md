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

The Runtime owns the production layout deterministically:

1. render exactly one **front full-body** image;
2. render exactly one **side-profile full-body** image;
3. render exactly one **back full-body** image;
4. derive the **face close-up** from the generated front view so the face is literally the same front identity;
5. compose those four panels into one landscape production reference sheet in fixed order.

The three model renders use the same canonical identity prompt, the same base seed and the same fixed wardrobe/color constraints. Runtime phrases each generation as one ordinary full-length studio photograph containing exactly one human figure, without using `character reference`, plural `views`, `turnaround`, `collage`, `contact sheet` or similar layout-trigger words. This moves structural correctness out of model free-form layout generation and into deterministic Runtime composition. For compatibility with older authored prompts, Runtime may deterministically remove only Runtime-owned layout clauses before execution; it must preserve the stable visual identity content.

Do not generate a single mood portrait, action scene, couple image or lifestyle scene. Narrative relationships and temporary story props must not enter the stable character identity prompt.

## Scene asset contract

Generate a clean environment identity reference image. Show the stable spatial layout, architecture/interior direction, materials, fixed landmarks, lighting identity and color palette derived from the localized storyboard. Do not add characters just because characters appear in the scene's story shots. The purpose is reusable scene identity, not reenacting a shot.

## Prop asset contract

Generate an isolated prop identity reference on a clean neutral background. Clearly show form, scale, material, color and signature details. Do not add hands or people unless they are indispensable to understanding scale; prefer a clean product/concept reference.

## Negative constraints

Z-Image Turbo's current local workflow uses zeroed negative conditioning. Therefore semantic exclusions (extra people, temporary props, text/watermarks, scene-specific backgrounds) must also be written directly into `image_prompt` as explicit `Do not ...` constraints. `negative_prompt` is still returned and persisted for audit/future adapters, but the Runtime may inline it as hard exclusions rather than using a separate negative conditioning encoder. Character layout vocabulary is the exception: do not put it in either prompt field; Runtime owns orientation and composition.

## Separation

- Prompt Skill: analyzes storyboard evidence and authors final image-model prompt.
- ComfyUI Runtime: executes the compiled stable identity plus deterministic single-person orientation constraints and persists the resulting media.
- Runtime must not infer relationships, invent another person, rewrite the asset identity or replace the prompt with a generic template. Its only compatibility normalization is stripping legacy Runtime-owned layout clauses before character execution.

