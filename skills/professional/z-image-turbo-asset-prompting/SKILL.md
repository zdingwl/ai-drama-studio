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

A Character asset is one landscape production reference sheet containing exactly this useful layout:

1. **front full-body view** — neutral standing pose;
2. **side full-body view** — neutral standing profile;
3. **back full-body view** — neutral standing pose;
4. **face close-up** — larger front-facing head/shoulders portrait showing hair, eyes, nose, mouth and neutral expression.

This is intentionally **three full-body views plus a facial close-up**. Do not generate four equal full-body directions. Do not generate a single mood portrait, action scene, couple image or lifestyle scene.

All four panels must depict the **same character** with the same face, hairstyle, body proportions, wardrobe and colors. Use a clean white or very light neutral studio background, clear spacing, no text labels, no watermark, no props unless the asset identity absolutely requires one.

The final Character `image_prompt` must literally contain the anchor phrases `front full-body view`, `side full-body view`, `back full-body view`, `face close-up`, and `same character` so the server can fail closed when the layout contract is missing.

## Scene asset contract

Generate a clean environment identity reference image. Show the stable spatial layout, architecture/interior direction, materials, fixed landmarks, lighting identity and color palette derived from the localized storyboard. Do not add characters just because characters appear in the scene's story shots. The purpose is reusable scene identity, not reenacting a shot.

## Prop asset contract

Generate an isolated prop identity reference on a clean neutral background. Clearly show form, scale, material, color and signature details. Do not add hands or people unless they are indispensable to understanding scale; prefer a clean product/concept reference.

## Negative constraints

Z-Image Turbo's current local workflow uses zeroed negative conditioning. Therefore critical exclusions must also be written directly into `image_prompt` as explicit `Do not ...` constraints. `negative_prompt` is still returned and persisted for audit/future adapters, but the Runtime may inline it as hard exclusions rather than using a separate negative conditioning encoder.

## Separation

- Prompt Skill: analyzes storyboard evidence and authors final image-model prompt.
- ComfyUI Runtime: executes exactly that compiled prompt and persists the resulting media.
- Runtime must not infer relationships, invent another person, rewrite the asset identity or replace the prompt with a generic template.

