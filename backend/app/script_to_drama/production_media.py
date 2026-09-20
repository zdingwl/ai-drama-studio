"""Script-to-drama media stages: reuse model runtimes, not Replica persistence.

Image model selection differs between ComfyUI (model_name) and Seedream
(character_pipeline_model_name). FFmpeg concat needs actual line breaks. Keep
these media-specific details isolated from text preproduction and H3 prompting.
"""

import json
import subprocess
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.errors import AppError
from app.p16.media import probe_video, sha256_file
from app.replica_pipeline.asset_images import asset_image_runtime
from app.replica_pipeline.image_model_skills import selected_image_model_prompt_skill
from app.script_localization.providers import ScriptLocalizationProvider
from app.script_to_drama import production as base
from app.script_to_drama.schemas import AssetPromptBatch, GeneratedAsset, GeneratedClip
from app.skills.models import Capability
from app.workflow.models import Task, TaskStatus
from app.workflow.provider_service import ProviderDispatchResult, dispatch_provider_call
from app.workflow.schemas import TaskWorkerRead
from app.workflow.task_service import TaskCancelled, mark_task_failed, mark_task_succeeded
from app.workflow.worker import TaskExecutionContext

TASK_TYPE = base.TASK_TYPE


def runtime_model_name(runtime: object, asset_type: str) -> str:
    """Select a configured model on both supported image runtimes."""
    default = str(getattr(runtime, "model_name", "") or "").strip()
    character = str(getattr(runtime, "character_pipeline_model_name", "") or "").strip()
    name = character if asset_type == "CHARACTER" and character else default
    if not name:
        raise AppError("SCRIPT_TO_DRAMA_IMAGE_MODEL_MISSING", "图片运行时未提供模型名称", status_code=409)
    return name


def _valid_checkpoint_assets(rows: list[dict]) -> list[dict]:
    root = get_settings().artifact_root.resolve()
    checked: list[dict] = []
    for row in rows:
        asset = GeneratedAsset.model_validate(row)
        for media in asset.media:
            path = (root / media.storage_relpath).resolve()
            if root not in path.parents or not path.is_file() or base._file_sha(path) != media.sha256:
                return []
        checked.append(asset.model_dump(mode="json"))
    return checked


def _run_asset_images(context: TaskExecutionContext, task: TaskWorkerRead) -> tuple[dict, list[str]]:
    with context.session_factory() as db:
        project, artifacts, contents = base._assert_fresh(db, task, "asset_images")
        specs = base._entity_specs(contents[0])
        provider = ScriptLocalizationProvider(get_settings(), project.source_understanding_provider)
        binding, prompt_skill = selected_image_model_prompt_skill()
        runtime = asset_image_runtime()
        runtime.assert_ready(require_character_edit=any(s["asset_type"] == "CHARACTER" for s in specs))

    previous = _valid_checkpoint_assets(list(task.checkpoint_json.get("results") or []))
    completed = {item["target_entity_id"] for item in previous}
    results = list(previous)
    jobs = list(task.checkpoint_json.get("provider_job_ids") or [])

    # Re-author bounded batches after resuming; do not trust a partial JSON result.
    for start in range(0, len(specs), base.MAX_PROMPT_BATCH):
        batch = specs[start:start + base.MAX_PROMPT_BATCH]
        pending = [item for item in batch if item["target_entity_id"] not in completed]
        if not pending:
            continue
        prompt = (
            f"为图片模型 {binding.model_id} 编译资产 Prompt；逐个覆盖指定 target_entity_id。"
            "单人物稳定视觉身份；空场景；独立道具。image_prompt 英文，review_prompt_zh 中文。"
            "不要添加画面中不存在的角色，也不要让图片模型自行排版人物多视图。输入："
            + json.dumps(pending, ensure_ascii=False)
        )

        def prompt_remote(_job, request=prompt):
            authored, remote_id = provider.generate(
                skill_id=prompt_skill.id,
                prompt=request,
                output_model=AssetPromptBatch,
                max_output_tokens=8192,
            )
            return ProviderDispatchResult(value=authored.model_dump(mode="json"), remote_job_id=remote_id)

        with context.session_factory() as db:
            _, fresh, _ = base._assert_fresh(db, task, "asset_images")
            prompt_job, dispatched = dispatch_provider_call(
                db, task_id=task.id, provider=provider.provider_name, model=provider.model_name,
                capability=Capability.MODEL_PROMPTING,
                payload={"task": TASK_TYPE, "stage": "asset_prompt", "entities": [s["target_entity_id"] for s in pending],
                         "skill": [prompt_skill.id, prompt_skill.version, binding.prompt_contract]},
                artifact_id=fresh[0].id, remote_call=prompt_remote,
            )
        authored = AssetPromptBatch.model_validate(dispatched.value)
        authored_map = {item.target_entity_id: item for item in authored.assets}
        if len(authored_map) != len(authored.assets) or set(authored_map) != {item["target_entity_id"] for item in pending}:
            raise AppError("SCRIPT_TO_DRAMA_ASSET_PROMPT_COVERAGE_INVALID", "图片 Prompt 未逐项覆盖当前资产批次", status_code=502)
        jobs.append(prompt_job.id)

        for spec in pending:
            item = authored_map[spec["target_entity_id"]]
            asset_id = f"asset:{base._hash([task.project_id, spec['target_entity_id']])[:24]}"

            def image_remote(_job, current=spec, authored_item=item, current_id=asset_id):
                if current["asset_type"] == "CHARACTER":
                    image = runtime.generate_character_sheet(
                        project_id=task.project_id, task_id=task.id, asset_id=current_id,
                        prompt=authored_item.image_prompt, negative_prompt=authored_item.negative_prompt,
                    )
                else:
                    image = runtime.generate(
                        project_id=task.project_id, task_id=task.id, asset_id=current_id,
                        prompt=authored_item.image_prompt, negative_prompt=authored_item.negative_prompt,
                        width=current["width"], height=current["height"],
                    )
                return ProviderDispatchResult(value=image, remote_job_id=image.remote_job_id)

            with context.session_factory() as db:
                _, fresh, _ = base._assert_fresh(db, task, "asset_images")
                job, image_result = dispatch_provider_call(
                    db, task_id=task.id, provider=runtime.provider_name,
                    model=runtime_model_name(runtime, spec["asset_type"]),
                    capability=Capability.ASSET_IMAGE_GENERATION,
                    payload={"task": TASK_TYPE, "stage": "asset_image_runtime",
                             "entity": spec["target_entity_id"], "asset_type": spec["asset_type"],
                             "prompt_sha256": base._hash(item.image_prompt), "runtime": runtime.profile()},
                    artifact_id=fresh[0].id, remote_call=image_remote,
                )
            image = image_result.value
            if spec["asset_type"] == "CHARACTER":
                media = base._derive_character_media(task.project_id, image)
            else:
                media = base._simple_media(image, "LAYOUT" if spec["asset_type"] == "SCENE" else "DETAIL")
            asset = GeneratedAsset(
                target_asset_id=asset_id, target_entity_id=spec["target_entity_id"],
                asset_type=spec["asset_type"], display_name=spec["display_name"],
                image_prompt=item.image_prompt, negative_prompt=item.negative_prompt,
                review_prompt_zh=item.review_prompt_zh, media=media,
            )
            results.append(asset.model_dump(mode="json"))
            jobs.append(job.id)
            completed.add(spec["target_entity_id"])
            context.checkpoint(
                {"stage": "asset_images", "phase": "runtime", "completed": len(results),
                 "results": results, "provider_job_ids": jobs},
                progress_percent=min(95, 5 + int(len(results) * 90 / len(specs))),
            )

    if len(results) != len(specs) or {s["target_entity_id"] for s in specs} != completed:
        raise AppError("SCRIPT_TO_DRAMA_ASSET_IMAGES_INCOMPLETE", "资产图未覆盖全部定义", status_code=422)
    return {
        "target_assets_definition_artifact_id": artifacts[0].id,
        "image_model_id": binding.model_id,
        "prompt_skill_id": prompt_skill.id, "prompt_skill_version": prompt_skill.version,
        "prompt_contract": binding.prompt_contract,
        "assets": results,
    }, jobs


def write_concat_manifest(paths: list[Path], destination: Path) -> None:
    """FFmpeg concat demuxer requires one physical line per clip, not literal \\n."""
    if not paths:
        raise ValueError("empty concatenation")
    lines: list[str] = []
    for path in paths:
        # FFmpeg concat quoting: close quote, backslash-escape apostrophe, reopen quote.
        escaped = str(path.resolve()).replace("'", "'\\''")
        lines.append("file '" + escaped + "'" + chr(10))
    destination.write_text("".join(lines), encoding="utf-8")


def _run_post(context: TaskExecutionContext, task: TaskWorkerRead) -> tuple[dict, list[str]]:
    with context.session_factory() as db:
        _, artifacts, contents = base._assert_fresh(db, task, "post")
        selection = contents[0]
    if selection.get("review_status") != "ACCEPTED":
        raise AppError("SCRIPT_TO_DRAMA_POST_REVIEW_REQUIRED", "正式选片未经人工确认", status_code=409)
    clips = [GeneratedClip.model_validate(item) for item in selection.get("clips", [])]
    if not clips:
        raise AppError("SCRIPT_TO_DRAMA_SELECTION_EMPTY", "正式选片为空", status_code=409)
    root = get_settings().artifact_root.resolve()
    paths: list[Path] = []
    for clip in clips:
        path = (root / clip.storage_relpath).resolve()
        if root not in path.parents or not path.is_file() or base._file_sha(path) != clip.sha256:
            raise AppError("SCRIPT_TO_DRAMA_SELECTED_MEDIA_STALE", "选片媒体缺失或文件校验失败", status_code=409)
        paths.append(path)
    output_rel = f"script_to_drama/final/{task.project_id}/{task.id}/final.mp4"
    output = (root / output_rel).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = output.with_suffix(".concat.txt")
    write_concat_manifest(paths, manifest)
    try:
        subprocess.run([
            get_settings().ffmpeg_binary, "-y", "-f", "concat", "-safe", "0", "-i", str(manifest),
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", str(output),
        ], check=True, capture_output=True, text=True, timeout=3600)
        media = probe_video(output)
    except Exception as exc:
        output.unlink(missing_ok=True)
        raise AppError("SCRIPT_TO_DRAMA_POST_FAILED", "FFmpeg 合成失败或成片媒体校验失败", status_code=502) from exc
    finally:
        manifest.unlink(missing_ok=True)
    context.checkpoint({"stage": "post", "completed": 1, "results": [output_rel], "provider_job_ids": []}, progress_percent=95)
    return {
        "generation_selection_artifact_id": artifacts[0].id, "storage_relpath": output_rel,
        "sha256": sha256_file(output), "mime_type": "video/mp4",
        "duration_us": media.duration_us, "width": media.width, "height": media.height,
        "codec_name": media.codec_name,
    }, []


def run_stage_task(factory: sessionmaker[Session], task_id: str) -> None:
    """Media-stage executor; other stages use the existing production executor."""
    with factory() as db:
        task = db.get(Task, task_id)
        if task is None or task.task_type != TASK_TYPE:
            return
        stage = str(task.checkpoint_json.get("stage") or "")
    if stage not in {"asset_images", "post"}:
        return base.run_stage_task(factory, task_id)

    worker_id = f"script-to-drama-media-{uuid4()}"
    with factory() as db:
        claimed = base._claim(db, task_id, worker_id)
        if claimed is None:
            return
        snapshot = TaskWorkerRead.model_validate(claimed)
    context = TaskExecutionContext(factory, snapshot.id, worker_id)
    try:
        content, jobs = (_run_asset_images(context, snapshot) if stage == "asset_images"
                         else _run_post(context, snapshot))
    except TaskCancelled:
        return
    except AppError as exc:
        with factory() as db:
            mark_task_failed(db, snapshot.id, safe_error=f"剧本生成短剧媒体生产失败（{exc.code}）：{exc.message}", worker_id=worker_id)
        return
    except Exception as exc:
        with factory() as db:
            mark_task_failed(db, snapshot.id, safe_error=f"剧本生成短剧媒体生产异常（{type(exc).__name__}）", worker_id=worker_id)
        return
    with factory() as db:
        done = mark_task_succeeded(db, snapshot.id, worker_id=worker_id)
    if done.status == TaskStatus.CANCELLED:
        return
    try:
        with factory() as db:
            base._publish(db, snapshot.id, stage, content, jobs)
    except AppError as exc:
        with factory() as db:
            db.rollback()
            base._mark_publish_failed(db, snapshot.id, f"媒体发布失败（{exc.code}）：{exc.message}")
    except Exception as exc:
        with factory() as db:
            db.rollback()
            base._mark_publish_failed(db, snapshot.id, f"媒体发布异常（{type(exc).__name__}）")
