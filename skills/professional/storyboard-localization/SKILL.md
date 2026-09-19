# Replica Storyboard Localization

## Purpose

Turn the accepted Source Video Snapshot into one coherent, production-ready target storyboard for a specific language and region.

This Skill is not literal translation, not cosmetic renaming, and not free-form story rewriting. It performs **function-preserving localization**: preserve the source episode's causal skeleton, shot identity, dramatic function, relationship logic, and evidence/action dependencies while redesigning the target-world realization so it feels native to the configured market.

The result must be usable by downstream asset, dialogue, and video-generation stages without asking those stages to repair cultural incoherence, timing, identity drift, or continuity mistakes.

## Hard input

`CURRENT SOURCE_VIDEO_SNAPSHOT` only, plus project:

- `target_language`
- `target_region`
- `scene_strategy`
- `visual_style`

Source facts remain source facts. Target design is created only in the target namespace.

## Runtime provider

Step 2 currently runs through Volcengine Ark / Doubao. It does **not** inherit the Step 1 source-understanding provider.

The provider may author target-world and shot semantics, but it may not invent Artifact IDs or stable target entity IDs. Those are server-owned.

## Three-layer adaptation boundary

Treat every localization decision as one of three layers.

### 1. Foundation — frozen source truth

Never silently alter:

- episode and shot order;
- source shot anchor identity;
- canonical utterance identity and source text;
- source start/end/duration provenance;
- structured source camera facts;
- core relationship graph;
- causal order of story events;
- evidence ownership and action consequences;
- who knows what at a given point in the story, unless the source itself changes that state.

If an apparently cultural change would alter one of these, it is no longer localization.

### 2. Story function — preserve function, not expression

Preserve what each beat **does**:

- pressure introduced or increased;
- information revealed or concealed;
- status or power changed;
- relationship tested or redefined;
- action attempted and consequence produced;
- setup, payoff, reversal, hook, or reaction function;
- why a prop, location, social custom, amount of money, or form of address matters to the conflict.

A target realization may look very different from the source if it performs the same story function.

### 3. Surface realization — redesign for the target market

This layer may change coherently:

- names and forms of address;
- professions and social presentation when needed for plausibility;
- housing type, architecture, furnishings, signage, brands, currency, and local objects;
- wardrobe, grooming, visible styling, and non-source actor appearance;
- cultural customs, etiquette, food, gifts, transport, schooling, workplace conventions, and public behavior;
- idioms, register, humor, emotional phrasing, and conversational rhythm;
- shot-local blocking and visual detail, provided source shot identity and camera facts remain intact.

Do not over-localize neutral details merely to prove that localization happened.

## Global planning before shot batches

Read the complete Source Snapshot before rewriting shots.

First produce one complete target-world plan covering every entity used across all episodes:

- `world_design_zh`
- `continuity_rules_zh`
- every Character
- every Scene
- every Prop

The plan must be concrete enough to execute visually. Avoid placeholders such as "same as source", "local equivalent", or "similar amount".

### Character plan

For each character, lock:

- localized full name and aliases actually needed by the story;
- family/relationship naming logic;
- social identity and status cues;
- age band when supported by source;
- target-world appearance, hair, body presentation, wardrobe baseline, and distinctive stable features;
- expected address/register relationships with other characters.

Target language does not imply ethnicity. Do not force a single ethnicity, immigrant framing, or stereotype because the source is Chinese or because the target language is English.

### Scene plan

For each scene, lock:

- target location identity;
- address/room naming when relevant;
- architecture and spatial layout;
- fixed landmarks and furniture;
- materials, lighting baseline, signage, and region-specific visual cues only where useful;
- room-to-room or exterior/interior relationships needed for continuity.

A scene must remain spatially usable across all shots that reference it.

### Prop plan

For each prop, lock:

- localized name;
- story function;
- owner/custodian when relevant;
- target-market form, material, scale, color, packaging, denomination, or interface;
- continuity-critical state changes.

When localizing money, documents, gifts, medications, devices, vehicles, school/work items, or legal/administrative objects, preserve the **conditions that make the conflict work**, not merely the noun.

## Functional localization ledger

Before choosing a culturally loaded replacement, reason through:

1. What source fact is locked?
2. What dramatic function does this element serve?
3. What target-market convention can perform that function naturally?
4. What downstream continuity does the replacement create?
5. Does the replacement accidentally change status, legality, evidence, stakes, chronology, or relationship meaning?

For high-risk elements, internally consider multiple plausible target realizations and choose one coherent solution. Return only the selected plan; do not emit competing worlds.

If no safe local equivalent exists, prefer a neutral, believable target formulation over an invented stereotype.

## Dialogue transcreation

`target_dialogue` is spoken target-language dialogue. `target_dialogue_zh` is Chinese review metadata only.

Dialogue must preserve:

- speaker intent;
- relationship and status;
- information payload;
- subtext and pressure;
- emotional direction;
- source utterance identity.

Dialogue should sound like speech from the target region, not translated prose.

Localize:

- honorifics, kinship address, pronouns, titles;
- contractions and conversational syntax;
- idioms and culturally specific references;
- politeness, confrontation, intimacy, and status register;
- jokes or indirect phrasing when the source function requires them.

Do not add explanatory dialogue for cultural facts that the target audience would naturally understand. Do not preserve source-language idioms word-for-word when the dramatic function can be expressed more naturally.

## Target timeline contract

Source shot timing is immutable provenance, not the target cut timeline.

Every localized shot must return a positive `target_duration_ms` planned from:

- localized spoken dialogue;
- listening/reaction time;
- target blocking and action;
- camera rhythm;
- necessary visual comprehension.

The server lays target shots out continuously per episode in source shot order.

Provider-authored `target_duration_ms` is the creative pacing proposal, not an unsafe hard ceiling. After the final localized dialogue is known, the server computes a deterministic minimum executable duration for every dialogue-owning shot from the speech estimate plus basic entry/exit and inter-line cadence slack. If the provider duration is shorter, the server may only expand it upward; it must never shrink a valid provider duration or modify source timing to make dialogue fit.

Every canonical utterance is spoken exactly once in one deterministic owner shot. Cross-shot source dialogue must not become duplicated target dialogue.

The localized spoken line must fit the target speech window at no more than approximately 4 whitespace-delimited words per second or 6 CJK characters per second. Leave room for breath, interruption, listening, and reaction; do not solve a bad fit by forcing unnatural speech.

A longer target shot is valid storyboard structure. Downstream model-specific prompting may split long target shots into executable generation segments, but it must not cut through a planned speech window.

H3 Prompt Skill must consume finalized target timing. It must not rewrite, accelerate, or duplicate finalized dialogue.

## Shot localization contract

Shot batches consume the frozen target world and may not redesign it.

For each source shot:

- preserve source shot identity and order;
- preserve structured source camera facts;
- preserve the beat's dramatic function;
- preserve the action/consequence relationship;
- realize the frozen target characters, scene, props, wardrobe, and naming;
- make blocking, reactions, and object use causally legible;
- write `localized_visual_description_zh` as the target shot itself, not as a comparison to the source;
- write `camera_description_zh` as clear Chinese review prose consistent with the structured camera facts;
- plan `target_duration_ms` from the target realization.

Do not copy source actor appearance, furniture, signs, brands, money, or cultural texture by default. Equally, do not replace a neutral detail unless the target version benefits from doing so.

### Performance causality

Keep visible reactions after their triggers:

- a facial reaction after information is heard or seen;
- physical movement after contact, force, or decision;
- tears, laughter, panic, recovery, or silence after the causal beat;
- prop state changes after the action that changes them.

Do not use localization as permission to reorder cause and effect.

## Continuity locks

`continuity_rules_zh` should contain only useful cross-shot invariants, such as:

- identity and naming;
- wardrobe state;
- wounds, dirt, makeup, wetness, or other persistent body state;
- prop ownership and prop state;
- geography, room relationships, and entrances/exits;
- vehicle or device state;
- information/knowledge state when visually relevant;
- address/register rules;
- currency/amount conventions;
- stable visual style and protected camera-axis facts when needed.

Continuity rules are not a place to restate the whole plot.

## Batching and identity

The validated global plan is frozen before the first shot batch.

Every batch receives the same complete plan. Batches return only their assigned shots and dialogue. They must not independently rename, redesign, or reinterpret characters, scenes, or props.

Batches:

- may not cross Episode boundaries;
- may not split a cross-shot utterance across different localization calls;
- must exactly cover their assigned source shot and utterance IDs;
- may not create new source IDs or target IDs.

Checkpointed completed batches are reusable only when source/configuration/contracts are unchanged.

## Output language contract

- world, entity, visual, camera, and continuity review prose: Simplified Chinese;
- spoken dialogue: `target_language`;
- dialogue review translation: Simplified Chinese;
- target entity names may remain in the target language;
- proper nouns, brands, addresses, and currency notation may remain in their natural target-market form.

## Failure conditions

Fail closed when any of the following occurs:

- missing/stale Source Snapshot;
- incomplete or duplicate ID coverage;
- global plan drift across shot batches;
- identity/name drift;
- target dialogue without a valid deterministic owner shot;
- target shot timing that is non-positive or inconsistent after server normalization;
- cultural replacement that changes locked story causality or relationship meaning;
- provider output that invents unsupported source facts;
- review prose not usable by Chinese reviewers.

When an output is repairable, correct only the failed dimension. Preserve already valid world, identity, continuity, and shot decisions.

## Review and publication

Generation produces a `NEEDS_REVIEW` candidate.

Only explicit ACCEPT publishes CURRENT `TARGET_STORYBOARD`.

Storyboard revisions maintain separate visual and dialogue projection fingerprints. Dialogue-only revisions may deterministically rebind persisted asset media to the new storyboard lineage, but they must still invalidate downstream H3 prompts and generated video.

## Quality checklist

Before returning a candidate, verify:

- the target version is culturally plausible without becoming stereotyped;
- story function is preserved even where surface expression changes;
- every character, location, prop, name, address, amount, and relationship convention agrees globally;
- every shot is visually executable and causally legible;
- dialogue sounds native to the target region and preserves intent/subtext;
- every utterance is spoken once;
- target timing is sufficient for speech, action, reaction, and camera rhythm after deterministic server minimum-duration normalization;
- source provenance remains intact;
- no downstream stage is being asked to repair a localization decision that belongs here.
