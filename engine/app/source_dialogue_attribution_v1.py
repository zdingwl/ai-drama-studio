"""D-ORCA audio-visual speaker attribution for canonical source dialogue.

This module keeps the heavy D-ORCA runtime outside the web process contract:
- GET/read paths only inspect a materialized artifact and never invoke a model;
- the explicit compile command invokes the provider;
- D-ORCA may attribute WHO/WHEN/WHAT, but WHAT never overwrites canonical ASR/OCR text;
- artifacts are anchored to the current BreakdownRun + ShotRevision and become STALE when
  those source anchors change.

The official D-ORCA repository currently exposes research inference through
``qwenvl/train/eval_dorca.py`` rather than a stable HTTP API.  The default provider therefore
runs that script in a separately configured Python environment/repository and consumes its
``test_results_rank0.json`` output.  Production deployments may inject another callable with
the same JSON contract without changing source-remake business logic.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections import defaultdict
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select

from engine.app.breakdown_read_model_contract_v1 import BreakdownReadModelV1
from engine.app.breakdown_read_model_v1 import load_episode_breakdown_read_model_v1
from engine.app import studio_v2
from engine.app.studio_v2 import Episode, Project, get_session


DORCA_ATTRIBUTION_SCHEMA_VERSION = "source-dialogue-attribution-v1"
DORCA_ARTIFACT_FILENAME = "dorca-attribution-v1.json"
DORCA_MODEL_PROFILE = "d-orca-8b-0210"


class DOrcaDialogueAttributionError(RuntimeError):
    """D-ORCA request, response, or source anchoring is invalid."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DOrcaAttributionItemV1(_StrictModel):
    dialogue_group_id: str = Field(min_length=1)
    scene_ordinal: int = Field(ge=1)
    speaker_ref: str | None = Field(default=None, pattern=r"^P[1-9][0-9]*$")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    mode: Literal["ON_CAMERA", "OFFSCREEN", "VOICE_OVER", "UNKNOWN"] = "UNKNOWN"
    heard_text: str | None = None


class DOrcaAttributionArtifactV1(_StrictModel):
    schema_version: Literal["source-dialogue-attribution-v1"] = DORCA_ATTRIBUTION_SCHEMA_VERSION
    status: Literal["READY", "READY_WITH_WARNINGS"]
    provider: Literal["D_ORCA"] = "D_ORCA"
    model_profile: str = DORCA_MODEL_PROFILE
    project_id: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    source_breakdown_run_id: str = Field(min_length=1)
    source_shot_revision_id: str = Field(min_length=1)
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    warnings: list[str] = Field(default_factory=list)
    items: list[DOrcaAttributionItemV1] = Field(default_factory=list)


class DOrcaAttributionReadV1(_StrictModel):
    state: Literal["MISSING", "READY", "STALE"]
    episode_id: str = Field(min_length=1)
    source_shot_revision_id: str = Field(min_length=1)
    message: str
    artifact: DOrcaAttributionArtifactV1 | None = None


class _ProviderItemV1(_StrictModel):
    dialogue_group_id: str = Field(min_length=1)
    speaker_ref: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    mode: Literal["ON_CAMERA", "OFFSCREEN", "VOICE_OVER", "UNKNOWN"] = "UNKNOWN"
    heard_text: str | None = None


class _ProviderResponseV1(_StrictModel):
    utterances: list[_ProviderItemV1] = Field(default_factory=list)


def _canonical_json_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _dedupe_text(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _episode_project(episode_id: str) -> tuple[Episode, Project]:
    with get_session() as session:
        episode = session.get(Episode, episode_id)
        if episode is None:
            raise LookupError("Episode 不存在")
        project = session.get(Project, episode.project_id)
        if project is None:
            raise LookupError("Project 不存在")
        session.expunge(episode)
        session.expunge(project)
        return episode, project


def _source_packet(episode_id: str) -> tuple[dict[str, Any], BreakdownReadModelV1, Episode, Project]:
    raw = load_episode_breakdown_read_model_v1(episode_id)
    if raw is None:
        raise DOrcaDialogueAttributionError("当前 Episode 还没有可用的原片理解结果")
    read_model = BreakdownReadModelV1.model_validate(raw)
    timeline = read_model.timeline
    if not timeline.is_current:
        raise DOrcaDialogueAttributionError("D-ORCA 只能消费当前 Breakdown 结果")
    episode, project = _episode_project(episode_id)

    identity_by_scene = {scene.scene_ordinal: scene for scene in read_model.identity.scenes}
    grouped: dict[str, dict[str, Any]] = {}
    scenes: list[dict[str, Any]] = []

    for scene in timeline.scenes:
        identity_scene = identity_by_scene.get(scene.ordinal)
        display_by_ref = {
            person.ref: person.display_name
            for person in identity_scene.people
        } if identity_scene is not None else {}
        candidates = [
            {
                "ref": person.ref,
                "display_name": display_by_ref.get(person.ref, person.display_name),
                "appearance": person.appearance,
            }
            for person in scene.people
        ]
        scenes.append({
            "scene_ordinal": scene.ordinal,
            "start_us": scene.start_us,
            "end_us": scene.end_us,
            "people": candidates,
        })
        for shot in scene.shots:
            for dialogue in shot.dialogue:
                group_id = str(getattr(dialogue, "dialogue_group_id", None) or "").strip()
                if not group_id:
                    continue
                row = grouped.setdefault(group_id, {
                    "dialogue_group_id": group_id,
                    "scene_ordinal": scene.ordinal,
                    "start_us": dialogue.start_us,
                    "end_us": dialogue.end_us,
                    "projection_texts": [],
                    "shot_ordinals": [],
                })
                row["start_us"] = min(int(row["start_us"]), int(dialogue.start_us))
                row["end_us"] = max(int(row["end_us"]), int(dialogue.end_us))
                row["projection_texts"].append(dialogue.text)
                row["shot_ordinals"].append(shot.ordinal)

    utterances: list[dict[str, Any]] = []
    for row in grouped.values():
        texts = _dedupe_text([str(value) for value in row.pop("projection_texts") if str(value).strip()])
        row["canonical_text_evidence"] = texts[0] if len(texts) == 1 else " | ".join(texts)
        row["shot_ordinals"] = list(dict.fromkeys(row["shot_ordinals"]))
        utterances.append(row)
    utterances.sort(key=lambda row: (int(row["start_us"]), str(row["dialogue_group_id"])))

    packet = {
        "episode_id": episode_id,
        "source_language": project.source_language,
        "source_breakdown_run_id": timeline.source_breakdown_run_id,
        "source_shot_revision_id": timeline.source_shot_revision_id,
        "scenes": scenes,
        "canonical_utterances": utterances,
    }
    return packet, read_model, episode, project


def _provider_prompt(packet: Mapping[str, Any]) -> str:
    serialized = json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"""You are the audio-visual dialogue attribution engine for a filmed short drama.
Use BOTH the visible video and its audio. Determine WHO says each supplied canonical utterance.

The canonical utterance IDs, text evidence and source times are supplied by the host system.
Do not create, delete, split, merge, translate or rewrite those canonical utterances.
The heard_text field is evidence only and will never replace host ASR/OCR text.

For every canonical_utterance return exactly one result. speaker_ref must be one of the P# refs
listed for that utterance's scene when a visible/known speaker can be identified. Use null when
the speaker cannot be tied to a listed person. Never invent another person ref.

Return ONLY one JSON object with this exact shape:
{{"utterances":[{{"dialogue_group_id":"...","speaker_ref":"P1 or null","confidence":0.0,"mode":"ON_CAMERA|OFFSCREEN|VOICE_OVER|UNKNOWN","heard_text":"optional evidence"}}]}}

<SOURCE_DIALOGUE_CONTEXT>{serialized}</SOURCE_DIALOGUE_CONTEXT>"""


def _extract_json_object(text: str) -> Mapping[str, Any]:
    cleaned = str(text or "").replace("<|im_end|>", "").strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < start:
        raise DOrcaDialogueAttributionError("D-ORCA 输出不包含 JSON object")
    try:
        payload = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as exc:
        raise DOrcaDialogueAttributionError("D-ORCA 输出 JSON 无法解析") from exc
    if not isinstance(payload, Mapping):
        raise DOrcaDialogueAttributionError("D-ORCA 输出必须是 JSON object")
    return payload


def request_dorca_json_v1(video_path: str, prompt: str) -> Mapping[str, Any]:
    """Invoke the official D-ORCA evaluation entrypoint in an isolated configured runtime."""

    repo_dir = Path(os.getenv("AI_DRAMA_DORCA_REPO", "")).expanduser()
    model_dir = Path(os.getenv("AI_DRAMA_DORCA_MODEL", "")).expanduser()
    if not str(repo_dir) or not repo_dir.is_dir():
        raise DOrcaDialogueAttributionError("AI_DRAMA_DORCA_REPO 未配置为有效的 D-ORCA 仓库目录")
    if not str(model_dir) or not model_dir.exists():
        raise DOrcaDialogueAttributionError("AI_DRAMA_DORCA_MODEL 未配置为有效的 D-ORCA 模型目录")
    entrypoint = repo_dir / "qwenvl" / "train" / "eval_dorca.py"
    if not entrypoint.is_file():
        raise DOrcaDialogueAttributionError("D-ORCA 官方 eval_dorca.py 不存在")
    source = Path(video_path)
    if not source.is_file():
        raise DOrcaDialogueAttributionError("D-ORCA 输入视频不存在")

    python_bin = os.getenv("AI_DRAMA_DORCA_PYTHON") or sys.executable
    timeout_seconds = max(60, int(os.getenv("AI_DRAMA_DORCA_TIMEOUT_SECONDS", "1800")))
    max_frames = max(16, int(os.getenv("AI_DRAMA_DORCA_MAX_FRAMES", "256")))
    interval = max(0.05, float(os.getenv("AI_DRAMA_DORCA_INTERVAL", "0.5")))

    with tempfile.TemporaryDirectory(prefix="ai-drama-dorca-") as temp_dir_raw:
        temp_dir = Path(temp_dir_raw)
        dataset_path = temp_dir / "request.json"
        output_dir = temp_dir / "output"
        run_name = "source-dialogue-attribution"
        dataset_path.write_text(json.dumps([{
            "video": str(source),
            "audio": str(source),
            "conversations": [
                {"from": "human", "value": "<video>\n" + prompt},
                {"from": "gpt", "value": ""},
            ],
        }], ensure_ascii=False), encoding="utf-8")
        command = [
            python_bin,
            str(entrypoint),
            "--run_test", "True",
            "--model_name_or_path", str(model_dir),
            "--model_base", str(model_dir),
            "--dataset_use", str(dataset_path),
            "--output_dir", str(output_dir),
            "--run_name", run_name,
            "--per_device_train_batch_size", "1",
            "--dataloader_num_workers", "0",
            "--report_to", "none",
            "--bf16", "True",
            "--model_max_length", "131072",
            "--video_min_frames", "1",
            "--video_max_frames", str(max_frames),
            "--base_interval", str(interval),
            "--max_new_tokens", "2048",
            "--train_type", "sft",
        ]
        env = dict(os.environ)
        env.setdefault("TOKENIZERS_PARALLELISM", "false")
        try:
            completed = subprocess.run(
                command,
                cwd=str(repo_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise DOrcaDialogueAttributionError("D-ORCA Runtime 启动或执行失败") from exc
        if completed.returncode != 0:
            tail = (completed.stderr or completed.stdout or "")[-2000:]
            raise DOrcaDialogueAttributionError(f"D-ORCA Runtime 失败: {tail}")
        result_path = output_dir / run_name / "test_results_rank0.json"
        if not result_path.is_file():
            raise DOrcaDialogueAttributionError("D-ORCA 没有生成 test_results_rank0.json")
        try:
            rows = json.loads(result_path.read_text(encoding="utf-8"))
            prediction = rows[0]["pred"]
        except (OSError, json.JSONDecodeError, IndexError, KeyError, TypeError) as exc:
            raise DOrcaDialogueAttributionError("D-ORCA 结果文件结构无效") from exc
        return _extract_json_object(str(prediction))


def normalize_dorca_response_v1(
    packet: Mapping[str, Any],
    raw_response: Mapping[str, Any],
    *,
    project_id: str,
) -> DOrcaAttributionArtifactV1:
    """Validate model output against host-owned canonical utterance/candidate identities."""

    try:
        response = _ProviderResponseV1.model_validate(raw_response)
    except ValidationError as exc:
        raise DOrcaDialogueAttributionError("D-ORCA 返回内容不符合 attribution contract") from exc

    expected = {str(row["dialogue_group_id"]): row for row in packet.get("canonical_utterances", [])}
    scene_people = {
        int(scene["scene_ordinal"]): {str(person["ref"]) for person in scene.get("people", [])}
        for scene in packet.get("scenes", [])
    }
    returned: dict[str, _ProviderItemV1] = {}
    warnings: list[str] = []
    for item in response.utterances:
        if item.dialogue_group_id in returned:
            raise DOrcaDialogueAttributionError("D-ORCA 重复返回同一 dialogue_group_id")
        if item.dialogue_group_id not in expected:
            warnings.append(f"D-ORCA 返回未知对白 {item.dialogue_group_id}，已忽略")
            continue
        returned[item.dialogue_group_id] = item

    normalized: list[DOrcaAttributionItemV1] = []
    for group_id, row in expected.items():
        scene_ordinal = int(row["scene_ordinal"])
        item = returned.get(group_id)
        speaker_ref = item.speaker_ref if item is not None else None
        if speaker_ref is not None and speaker_ref not in scene_people.get(scene_ordinal, set()):
            warnings.append(f"{group_id} 的 Speaker 不属于当前 Scene，已自动降级为 UNKNOWN")
            speaker_ref = None
        if item is None:
            warnings.append(f"{group_id} 未获得 D-ORCA 结果，保留后续 fallback")
        normalized.append(DOrcaAttributionItemV1(
            dialogue_group_id=group_id,
            scene_ordinal=scene_ordinal,
            speaker_ref=speaker_ref,
            confidence=item.confidence if item is not None else None,
            mode=item.mode if item is not None else "UNKNOWN",
            heard_text=item.heard_text if item is not None else None,
        ))

    input_fingerprint = _canonical_json_hash(packet)
    output_material = [item.model_dump(mode="json") for item in normalized]
    output_fingerprint = _canonical_json_hash({"input_fingerprint": input_fingerprint, "items": output_material})
    return DOrcaAttributionArtifactV1(
        status="READY_WITH_WARNINGS" if warnings else "READY",
        project_id=project_id,
        episode_id=str(packet["episode_id"]),
        source_breakdown_run_id=str(packet["source_breakdown_run_id"]),
        source_shot_revision_id=str(packet["source_shot_revision_id"]),
        input_fingerprint=input_fingerprint,
        output_fingerprint=output_fingerprint,
        warnings=_dedupe_text(warnings),
        items=normalized,
    )


def compile_dorca_dialogue_attribution_v1(
    episode_id: str,
    *,
    provider: Callable[[str, str], Mapping[str, Any]] | None = None,
) -> DOrcaAttributionArtifactV1:
    packet, _read_model, episode, project = _source_packet(episode_id)
    raw = (provider or request_dorca_json_v1)(episode.source_path, _provider_prompt(packet))
    return normalize_dorca_response_v1(packet, raw, project_id=project.id)


def attribution_artifact_path_v1(project_id: str, episode_id: str) -> Path:
    return studio_v2.episode_dir(project_id, episode_id) / "source-dialogue-attribution" / DORCA_ARTIFACT_FILENAME


def persist_dorca_dialogue_attribution_v1(artifact: DOrcaAttributionArtifactV1) -> Path:
    packet, _read_model, _episode, project = _source_packet(artifact.episode_id)
    if project.id != artifact.project_id:
        raise DOrcaDialogueAttributionError("D-ORCA artifact belongs to another Project")
    if str(packet["source_breakdown_run_id"]) != artifact.source_breakdown_run_id or str(packet["source_shot_revision_id"]) != artifact.source_shot_revision_id:
        raise DOrcaDialogueAttributionError("D-ORCA artifact is stale before persistence")
    if _canonical_json_hash(packet) != artifact.input_fingerprint:
        raise DOrcaDialogueAttributionError("D-ORCA artifact input fingerprint no longer matches current source facts")
    path = attribution_artifact_path_v1(artifact.project_id, artifact.episode_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(artifact.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    temp = path.with_name(path.name + ".tmp")
    temp.unlink(missing_ok=True)
    try:
        temp.write_text(serialized, encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    return path


def read_dorca_dialogue_attribution_v1(episode_id: str) -> DOrcaAttributionReadV1:
    packet, _read_model, _episode, project = _source_packet(episode_id)
    current_revision = str(packet["source_shot_revision_id"])
    path = attribution_artifact_path_v1(project.id, episode_id)
    if not path.is_file():
        return DOrcaAttributionReadV1(
            state="MISSING",
            episode_id=episode_id,
            source_shot_revision_id=current_revision,
            message="当前剧集还没有生成 D-ORCA 说话人归属结果。",
        )
    try:
        artifact = DOrcaAttributionArtifactV1.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise DOrcaDialogueAttributionError("已保存的 D-ORCA attribution artifact 无效") from exc
    current_input = _canonical_json_hash(packet)
    if (
        artifact.project_id != project.id
        or artifact.episode_id != episode_id
        or artifact.source_breakdown_run_id != str(packet["source_breakdown_run_id"])
        or artifact.source_shot_revision_id != current_revision
        or artifact.input_fingerprint != current_input
    ):
        return DOrcaAttributionReadV1(
            state="STALE",
            episode_id=episode_id,
            source_shot_revision_id=current_revision,
            message="原片理解或镜头版本已经变化，请显式重新运行 D-ORCA。",
            artifact=artifact,
        )
    return DOrcaAttributionReadV1(
        state="READY",
        episode_id=episode_id,
        source_shot_revision_id=current_revision,
        message="D-ORCA 说话人归属结果可用于当前原片事实。",
        artifact=artifact,
    )


def load_current_dorca_attribution_index_v1(
    episode_id: str,
    *,
    source_shot_revision_id: str,
) -> dict[str, dict[str, Any]]:
    """Read-only helper consumed by SourceDramaSnapshot speaker resolution."""

    try:
        read = read_dorca_dialogue_attribution_v1(episode_id)
    except (LookupError, DOrcaDialogueAttributionError, ValueError):
        return {}
    if read.state != "READY" or read.artifact is None or read.source_shot_revision_id != source_shot_revision_id:
        return {}
    return {
        item.dialogue_group_id: item.model_dump(mode="json")
        for item in read.artifact.items
        if item.speaker_ref is not None
    }


__all__ = [
    "DOrcaAttributionArtifactV1",
    "DOrcaAttributionItemV1",
    "DOrcaAttributionReadV1",
    "DOrcaDialogueAttributionError",
    "attribution_artifact_path_v1",
    "compile_dorca_dialogue_attribution_v1",
    "load_current_dorca_attribution_index_v1",
    "normalize_dorca_response_v1",
    "persist_dorca_dialogue_attribution_v1",
    "read_dorca_dialogue_attribution_v1",
    "request_dorca_json_v1",
]
