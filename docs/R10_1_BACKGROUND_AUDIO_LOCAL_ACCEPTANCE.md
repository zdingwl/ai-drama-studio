# R10.1 Safe Background Audio — Local Acceptance

This document is only for the dedicated R10.1 `audio-separator` runtime.

Repository CI proves the provider boundary, FFmpeg safety gates, timing mapping and fallback behavior. It does **not** prove that the configured separation model works well on the actual local GPU or real short-drama audio.

## 1. Install the dedicated runtime

Run from the repository root in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_audio_separator_runtime.ps1
```

This creates:

```text
.venv-audio-separator
```

It does not modify the main project `.venv`.

To rebuild this dedicated environment explicitly:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_audio_separator_runtime.ps1 -Reinstall
```

## 2. Start the worker

Keep this terminal open:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_audio_separator_runtime.ps1
```

Default runtime:

```text
http://127.0.0.1:7863
model = UVR-MDX-NET-Inst_HQ_5.onnx
```

The first real separation may download/load the configured model.

## 3. Run the real model self-check

Open a second PowerShell terminal:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check_audio_separator_runtime.ps1
```

PASS means all of these happened:

```text
worker reachable
→ audio-separator import ready
→ configured model loaded
→ one real WAV separation request completed
→ Instrumental output file materialized
→ output audio decodes when ffprobe is available
```

Do not mark the local runtime accepted from `/health` alone.

## 4. Optional model override

Use the same model name for start and check:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_audio_separator_runtime.ps1 -Model "YOUR_MODEL_FILENAME"
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check_audio_separator_runtime.ps1 -Model "YOUR_MODEL_FILENAME"
```

Studio can also be configured through:

```text
AI_DRAMA_BACKGROUND_AUDIO_MODEL
AI_DRAMA_BACKGROUND_AUDIO_BASE_URL
```

## 5. Product safety behavior

R10.1 never mixes raw source audio back into the localized episode.

```text
source Shot audio
→ Instrumental separation
→ SourceDramaSnapshot source-dialogue-window hard suppression
→ target-duration conform
→ conservative background mix under target dialogue
```

If this worker/model is unavailable or separation fails:

```text
TARGET_DIALOGUE_ONLY_FALLBACK
```

The already-valid target-dialogue R10 output remains usable and Episode assembly continues. Audio-separator infrastructure failure does not create a human ReviewIssue.

## 6. Real-project acceptance

After the self-check passes, run at least one real Episode and listen for:

```text
no residual source-language dialogue
ambient/action sounds remain useful
BGM does not overpower target dialogue
no obvious audio restart when one source Shot becomes multiple GenerationSegments
no clipping/pumping around target dialogue
final Episode timing remains aligned with subtitles and lip sync
```

Only after this real listening check should R10.1 local model quality be marked PASS.
