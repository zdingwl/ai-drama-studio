# Qwen Image Edit 2511 Character Orientation Prompting

## Role

This Professional Skill is the model-specific edit contract for the derived side and back panels of a Replica Character asset. It does **not** create a new character identity. The canonical front full-body image produced earlier in the same Step 3 run is the visual truth.

The normal character pipeline is:

```text
localized storyboard evidence
→ z-image-turbo-asset-prompting
→ Z-Image Turbo canonical FRONT master
→ qwen-image-edit-character-asset-prompting
→ Qwen Image Edit 2511 SIDE / BACK derivatives
→ deterministic front-derived FACE crop
→ fixed four-panel board
```

## Runtime profile

Current Windows production profile:

```text
UNET = qwen_image_edit_2511_fp8mixed.safetensors
CLIP = qwen_2.5_vl_7b_fp8_scaled.safetensors, type=qwen_image
VAE  = qwen_image_vae.safetensors
encoder = TextEncodeQwenImageEditPlus
reference method = FluxKontextMultiReferenceLatentMethod:index_timestep_zero
steps = 20
cfg = 4.0
sampler = euler
scheduler = simple
ModelSamplingAuraFlow shift = 3.1
```

## Hard visual truth

`Image 1` is the authoritative canonical front master. Qwen Image Edit receives that image directly. Side/back generation must not depend on same-seed text-to-image resemblance.

The edit instruction must lock all stable visible identity information from Image 1:

- facial structure and apparent age;
- hairstyle, hair color and skin tone;
- body proportions;
- upper garment type, sleeve length, fabric, pattern and color;
- lower-garment type and length;
- footwear presence, type and color.

Only orientation may change.

## Side contract

Produce one strict 90-degree left-facing full-body profile. Nose points left, shoulders are perpendicular to camera, head and both feet remain visible. Do not redesign any identity or wardrobe detail.

## Back contract

Produce one exact rear full-body view. Show the back of the head and body; the face must not be visible. Do not redesign any identity or wardrobe detail.

## Hard exclusions

- Never turn trousers into shorts, skirts or dresses, or vice versa.
- Never add/remove footwear or change footwear type.
- Never change hairstyle, age, body build or skin tone.
- Never add another person, temporary prop, text, watermark or story environment.
- Never fall back to independent side/back text-to-image sampling when the reference edit path is unavailable.

## Separation

The upstream Z-Image Prompt Skill owns the semantic/stable identity prompt used to create the front master. This Qwen Skill owns only reference-image orientation editing. The Runtime may deterministically instantiate the fixed side/back instruction from this contract, but may not invent additional character facts or silently switch models.
