import httpx

from app.core.errors import AppError
from app.p14.provider import IndexTTS25Provider, SynthesizedAudio


def synthesize_with_delivery(
    provider: IndexTTS25Provider,
    *,
    text: str,
    voice_id: str,
    acting_direction: str | None,
    emo_alpha: float,
    duration_factor: float,
) -> SynthesizedAudio:
    """Call IndexTTS-2.5 with explicit per-utterance acting controls.

    The spoken input remains the frozen Final Target Dialogue. Acting direction is sent only
    through IndexTTS emotion text; it is never concatenated into the dialogue itself.
    """

    if not 0.0 <= emo_alpha <= 1.0:
        raise AppError("P14_INDEXTTS_EMOTION_INVALID", "IndexTTS 情绪强度必须在 0.0 到 1.0 之间", status_code=422)
    if not 0.5 <= duration_factor <= 2.0:
        raise AppError("P14_INDEXTTS_DURATION_FACTOR_INVALID", "IndexTTS duration_factor 必须在 0.5 到 2.0 之间", status_code=422)

    ref_audio, _reference_sha = provider._reference_data_url(voice_id)
    extra_params: dict[str, object] = {
        "lang": provider.language_code,
        "text_normalization": True,
        "use_emo_text": True,
        "emo_alpha": emo_alpha,
    }
    normalized_direction = " ".join((acting_direction or "").split())
    if normalized_direction:
        extra_params["emo_text"] = normalized_direction
    payload = {
        "model": provider.model_name,
        "input": text,
        "response_format": provider.response_format,
        "ref_audio": ref_audio,
        "speed": duration_factor,
        "extra_params": extra_params,
    }
    try:
        response = httpx.post(
            f"{provider.base_url}/audio/speech",
            json=payload,
            headers={"Accept": "audio/wav"},
            timeout=provider.timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise AppError("P14_INDEXTTS_TRANSPORT_FAILED", "IndexTTS-2.5 服务连接失败", status_code=502) from exc
    if response.status_code >= 400:
        raise AppError(
            "P14_INDEXTTS_REJECTED",
            f"IndexTTS-2.5 返回 HTTP {response.status_code}",
            status_code=502,
        )
    if not response.content:
        raise AppError("P14_INDEXTTS_EMPTY_AUDIO", "IndexTTS-2.5 返回空音频", status_code=502)
    content_type = response.headers.get("content-type", "audio/wav").split(";", 1)[0].strip().lower()
    remote_job_id = response.headers.get("x-request-id") or response.headers.get("request-id")
    return SynthesizedAudio(
        audio_bytes=response.content,
        mime_type=content_type or "audio/wav",
        file_extension="wav",
        remote_job_id=remote_job_id,
    )
