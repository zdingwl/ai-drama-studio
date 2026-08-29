# Session Handoff — P2-E3 fail-soft runtime hardening

Date: 2026-08-29 13:16 +08:00
Repository: `zdingwl/ai-drama-studio`
Branch: `main`

## Trigger

Real local Episode rerun progressed through P2-E2 and then failed with:

```text
VLM Provider status=FAILED，P2 pipeline fail closed；P2-E3 contextual refinement inference failed
```

This proves the E2 path was no longer the immediate blocker. The failure happened in the second, text-only E3 refinement subprocess.

## Diagnosis

Before this change, `ContextualShotRefiner._run_subprocess()` used `subprocess.run(check=True)` and `refine()` converted any whole-subprocess exception into a generic FAILED result. `refine_e2_provider_result()` then converted that E3-only failure into a FAILED formal VLM ProviderResult, discarding an already-valid E2 visual result for the new Run.

That failure policy was too strict for the architecture: E2 is the continuous-video visual evidence layer; E3 is contextual quality refinement only. A broken E3 runtime should reduce refinement quality, not erase valid E2 semantics.

The isolated E3 runner also loaded Qwen before entering its per-Shot exception boundary. Model/device/runtime setup errors therefore terminated the whole subprocess before per-Shot fallback could occur.

## Implementation

### `scripts/run_breakdown_refinement_qwen3.py`

- runtime/model/device setup is now inside a fail-soft boundary;
- setup failure is serialized as one FAILED refinement record per exact Shot;
- each failed record stores sanitized `error_type`, `error_detail`, `failure_stage` and a Chinese `refinement_note` indicating that E2 is being preserved;
- item-level inference failures use the same per-Shot failure record shape;
- failed item generation triggers best-effort CUDA cache cleanup;
- the runner exits successfully after serializing E3 failures so the main process can consume them and fall back to E2.

### `engine/app/breakdown_p2_vlm_runtime_v1.py`

New formal failure policy:

```text
E2 READY + E3 READY
→ use grounded E3 semantics

E2 READY + E3 per-Shot failure
→ existing per-Shot E2 fallback

E2 READY + E3 whole runtime/subprocess/adapter failure
→ formal VLM remains READY
→ payload.semantic = validated E2 semantic
→ payload.e2_semantic = same E2 semantic
→ payload.contextual_refinement.status = FALLBACK_E2
→ warning + failure provenance retained

E2 not READY
→ still fail closed
```

New policy identifier:

```text
VLM_CONTEXTUAL_FAILURE_POLICY = e3-fail-soft-to-e2-v1
```

This does not create Final Character/Scene/Prop/Binding truth and does not relax any Character V10.1 gate.

### Tests

Added:

```text
engine/tests/v2/test_breakdown_p2_e3_failsoft.py
```

Coverage includes:

- whole E3 failure -> READY E2 fallback ProviderResult;
- exact E2 semantics and sidecar-compatible Evidence remain preserved;
- `FALLBACK_E2` provenance is written;
- E3 isolated runner serializes runtime-setup failure per Shot.

## Documentation

Updated:

```text
AGENTS.md
SKILL.md
```

Project stage status did not advance: E1/E2/E3 remain IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING; P2.6 remains NOT PASSED; E4 remains NEXT.

## Commits

```text
231210e8  fix(p2): make E3 refinement fail soft to E2 [skip ci]
02803336  fix(p2): fall back to E2 when E3 is unavailable [skip ci]
d54c2978  test(p2): cover E3 fail-soft fallback [skip ci]
7a6f3ed5  docs: record E3 fail-soft policy [skip ci]
7c5d9db4  docs: align E3 fail-soft behavior [skip ci]
```

## Validation truth

Hosted GitHub Actions were not used. This session did not execute the user's Windows/Qwen/CUDA runtime or local pytest. Do not claim E3 quality PASS, P2.6 PASS, or full Episode-context acceptance.

## Next action

Pull latest `main` and rerun the same Episode with the same parameters. Expected behavior:

- if E3 now runs, the pipeline continues normally;
- if E3 still has a runtime/model problem, the Breakdown should continue using E2 semantics instead of failing the complete VLM component;
- the resulting VLM provenance should show `contextual_refinement.status = FALLBACK_E2` for affected Shots/Run.

After the Run completes, inspect whether E3 actually refined any Shots or the Run fell back entirely to E2. Do not start P2-E4 until real E2/E3 behavior is visible and stable enough to judge.
