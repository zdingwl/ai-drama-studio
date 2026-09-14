# Replica Asset Image Generation

The localized storyboard is the semantic source. Extract only the people, locations and props actually used by shots, turn those entities into stable asset-local visual designs, compile the current image model's execution prompts, render real reference images, persist them in Studio storage, and expose them as `TargetReferenceMedia` with SHA256 and dimensions.

Text-only packets or `reference_media=[]` do not satisfy this skill.

## Review text is not the model prompt

Chinese review prose and image-model execution prompts are different contracts.

- `review_description_zh` is for Chinese human review. It should explain the stable visual identity of the character / scene / prop in clear Simplified Chinese.
- `image_prompt` is the execution prompt for the active image model. It may be English or otherwise model-optimized.
- Never feed abstract Chinese review prose directly to the image runtime as if it were already a model-specific prompt.
- Prompt compilation may concretize underspecified visual details into a stable production design, but it may not alter the localized entity's core identity, story function, target region, explicit appearance facts, shot order or dialogue.

## Current Flux.1 Schnell adapter

The default Windows runtime is local ComfyUI with Flux.1 Schnell. Before rendering, the adapter uses Volcengine Ark / Doubao to compile each localized entity into an asset-local visual design and concrete English Flux execution facts. The server then adds deterministic composition constraints for the asset type.

Character reference images must request exactly one fictional person, head-to-toe visible, neutral standing pose, front three-quarter view, neutral studio background, with a stable face / hair / body / base wardrobe identity. Scene reference images must be empty environment references with no people. Prop reference images must contain exactly one isolated object with no hands or people.

The current Flux Schnell workflow runs at CFG 1.0. Therefore important avoidance constraints are folded into the positive execution prompt instead of pretending that a separate negative-conditioning string is authoritative. `negative_prompt` remains useful as review/provenance data, but the positive prompt must itself contain the no-text / no-watermark / no-collage / no-duplicate / no-cropping and asset-type-specific exclusions that matter to rendering.

The Prompt Compiler must preserve exact target entity coverage. Missing, duplicate or invented target entity IDs fail closed before any image is rendered.

Human ACCEPT is required before publishing CURRENT `TARGET_ASSETS v2`.
