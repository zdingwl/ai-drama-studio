# Replica Asset Image Generation

The localized storyboard is the semantic source. Extract the people, locations and props actually used by shots, render real reference images, persist them in Studio storage, and expose them as `TargetReferenceMedia` with SHA256 and dimensions.

Text-only packets or `reference_media=[]` do not satisfy this skill.

The default Windows runtime is local ComfyUI. A model adapter may optimize the image execution prompt, but it may not change target identity or storyboard semantics.

Human ACCEPT is required before publishing CURRENT TARGET_ASSETS v2.
