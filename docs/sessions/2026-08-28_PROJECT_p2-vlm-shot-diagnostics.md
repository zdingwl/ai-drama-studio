# P2 VLM Shot diagnostics fix

Date: 2026-08-28

## Trigger

Real Windows P2 execution reached the Qwen3-VL checkpoint but failed with only:

`VLM Provider status=FAILED ... Shot 1 VLM inference failed`

The isolated runner captured the Shot exception but persisted only `error_type`; the Provider then discarded even that and emitted a generic warning.

## Change

- Added `scripts/run_breakdown_vlm_qwen3_diagnostic.py`.
  - Reuses the frozen Qwen3-VL model loading/inference functions.
  - Persists short per-Shot `error_type` + `error_detail` in the private JSONL transport.
- Added `engine/app/breakdown_p2_vlm_runtime_v1.py`.
  - Keeps VLM fail-closed behavior.
  - Surfaces Shot-level failure detail in Provider warnings/metadata.
  - Preserves the tail of a failed Qwen subprocess output when the whole subprocess crashes.
- Production P2 pipeline and local P2 CLI now use the diagnostic provider.
- Added unit coverage for diagnostic runner selection and failure-detail sanitization.

## Invariants preserved

- VLM must still be `READY` before complete anonymous Draft publication.
- No Final Character / Scene / Prop / Binding behavior changed.
- No Fusion semantic rule changed.
- P2.6 real-model acceptance remains NOT PASSED until a real short-drama full chain succeeds and is reviewed.
