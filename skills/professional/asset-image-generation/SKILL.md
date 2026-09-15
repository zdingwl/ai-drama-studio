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
→ z-image-turbo-asset-prompting@1.0.0
→ local ComfyUI
→ z_image_turbo_bf16.safetensors
```

The image Runtime executes the Skill-authored prompt. Runtime code may map that prompt into native ComfyUI nodes and inline hard exclusions required by the model profile, but may not re-author asset identity or replace it with a generic template.

## Character output

One Character asset image is a landscape production reference sheet containing:

1. front full-body view;
2. side full-body view;
3. back full-body view;
4. larger face close-up.

It is **three full-body views plus a face close-up**, not four full-body directions. The same person, face, hairstyle, proportions, wardrobe and colors must remain consistent. Use a clean light studio background; no couple composition, no story reenactment, no phone/lifestyle pose unless the identity itself requires a signature prop.

## Scene / Prop output

- Scene: stable environment identity, layout, landmarks, materials and lighting; no story characters.
- Prop: isolated object identity, form, scale, material, color and signature details; no unrelated person/environment.

## Publication

Text-only packets or `reference_media=[]` do not satisfy this skill. Generated media must be persisted in Studio storage and exposed as `TargetReferenceMedia` with SHA256 and dimensions.

Human ACCEPT is required before publishing CURRENT TARGET_ASSETS v2.
