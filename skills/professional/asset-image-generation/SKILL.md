# Replica Asset Image Generation

## Purpose

The localized storyboard is the semantic source. Step 3 is explicitly a three-part pipeline:

```text
extract used assets
→ execute the selected image model's Professional Prompt Skill against localized storyboard evidence
→ render the compiled prompt with the image Runtime
```

The orchestration Skill must never skip the middle step by directly concatenating entity prose into a generic image prompt.

## Hard input

Only CURRENT `TARGET_STORYBOARD v2` plus project visual style. Extract only Character / Scene / Prop entities actually referenced by shots or canonical target dialogue speaker bindings.

For every extracted asset, gather the target entity definition and the localized visual descriptions of the shots that actually reference it. This is the evidence supplied to the model-specific image Prompt Skill.

## Current image model binding

Current Windows default:

```text
Z-Image Turbo
→ z-image-turbo-asset-prompting@1.5.0
→ z_image_turbo_bf16.safetensors → canonical FRONT master
→ qwen-image-edit-character-asset-prompting@1.0.0
→ qwen_image_edit_2511_fp8mixed.safetensors → SIDE / BACK
→ local ComfyUI
```

The image Runtime executes the Skill-authored identity prompt. For Character assets, Runtime first generates one authoritative front full-body master with Z-Image Turbo. It then uploads that exact front image as Qwen Image Edit `Image 1`; the Qwen-specific Professional Skill locks identity, body, wardrobe and footwear while allowing only side/back orientation changes. The facial close-up is derived from the front master, and Runtime composes the final four-panel sheet deterministically. Runtime may not change the underlying identity facts.

## Character output

One Character asset image is a landscape production reference sheet containing:

1. front full-body view;
2. side full-body view;
3. back full-body view;
4. larger face close-up.

It is **three full-body views plus a face close-up**, not four independent text-to-image directions. The front full-body render is the identity master. Side/back are Qwen Image Edit derivatives that directly receive the front master as reference input and may change orientation only; they must preserve garment topology and footwear exactly. The face close-up is cropped from the front master; Runtime then composes the fixed four-panel sheet. Use a clean light studio background; no couple composition, no story reenactment, no phone/lifestyle pose unless the identity itself requires a signature prop.

## Scene / Prop output

- Scene: stable environment identity, layout, landmarks, materials and lighting; no story characters.
- Prop: isolated object identity, form, scale, material, color and signature details; no unrelated person/environment.

## Publication

Text-only packets or `reference_media=[]` do not satisfy this skill. Generated media must be persisted in Studio storage and exposed as `TargetReferenceMedia` with SHA256 and dimensions.

After generation, the server must validate managed `reference_media` completeness and CURRENT `TARGET_STORYBOARD` lineage. Validation success auto-publishes CURRENT `TARGET_ASSETS v2`; the ordinary asset workspace does not require a separate batch confirmation. Users inspect the published images directly and explicitly regenerate when correction is needed.
